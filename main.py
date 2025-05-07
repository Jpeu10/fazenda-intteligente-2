from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, Integer, String, Float, TIMESTAMP, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import requests
import paho.mqtt.client as mqtt
import os
from dotenv import load_dotenv

# 📌 Carregar variáveis do ambiente
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
MQTT_BROKER = os.getenv("MQTT_BROKER")

# 📌 Configuração do banco de dados PostgreSQL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# 📌 Definição das tabelas
class SensorData(Base):
    __tablename__ = "sensor_data"
    id = Column(Integer, primary_key=True)
    temperature = Column(Float)
    humidity = Column(Float)
    rain_mm = Column(Float)
    timestamp = Column(TIMESTAMP)

class Mission(Base):
    __tablename__ = "missions"
    id = Column(Integer, primary_key=True)
    drone_id = Column(Integer)
    status = Column(String(50))
    weather_conditions = Column(String(100))
    date = Column(TIMESTAMP)

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True)
    mission_id = Column(Integer, ForeignKey("missions.id"))
    gps_lat = Column(Float)
    gps_long = Column(Float)
    status_saude = Column(String(50))
    tipo_problema = Column(String(100))
    foto_url = Column(String)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    tipo_alerta = Column(String(100))
    data_detectada = Column(TIMESTAMP)

Base.metadata.create_all(bind=engine)

# 📌 Criando servidor FastAPI
app = FastAPI()

# 📌 Conexão com banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 📌 Rota para receber dados dos sensores
@app.post("/sensor-data/")
async def receive_sensor_data(data: dict, db: Session = Depends(get_db)):
    new_entry = SensorData(**data)
    db.add(new_entry)
    db.commit()
    return {"message": "Dados dos sensores armazenados!"}

# 📌 Rota para decidir se o drone pode decolar
@app.get("/drone-status/")
async def check_weather(db: Session = Depends(get_db)):
    latest_weather = db.query(SensorData).order_by(SensorData.id.desc()).first()
    if latest_weather.rain_mm > 0:
        return {"canTakeOff": False, "reason": "Está chovendo!"}
    return {"canTakeOff": True}

# 📌 Função para analisar imagem via Hugging Face
def analyze_image(image_url):
    response = requests.post("https://api.huggingface.co/models/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", json={"image": image_url})
    return response.json()

# 📌 MQTT para receber imagens do drone
def on_message(client, userdata, message):
    image_data = message.payload.decode("utf-8")
    result = analyze_image(image_data)
    
    if result["alert"]:
        save_alert(image_data["gps_lat"], image_data["gps_long"], result["problemType"])

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883)
mqtt_client.subscribe("drone/images")
mqtt_client.loop_start()

# 📌 Função para salvar alertas no banco
def save_alert(gps_lat, gps_long, problem_type):
    db = SessionLocal()
    new_alert = Alert(gps_lat=gps_lat, gps_long=gps_long, tipo_alerta=problem_type)
    db.add(new_alert)
    db.commit()
    db.close()

# 📌 Rota para obter alertas no frontend
@app.get("/alerts/")
async def get_alerts(db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.data_detectada.desc()).all()
    return alerts

# 📌 Rota para obter status do drone
@app.get("/drone-status/")
async def get_drone_status(db: Session = Depends(get_db)):
    mission = db.query(Mission).order_by(Mission.date.desc()).first()
    return {"droneStatus": mission.status, "lastMissionDate": mission.date}
