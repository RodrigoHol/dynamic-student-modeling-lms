const { Kafka, Partitioners } = require('kafkajs');

// Inicialización del cliente Kafka apuntando a la infraestructura local o de clúster
const kafka = new Kafka({
  clientId: 'lms-ingestion-gateway',
  brokers: [process.env.KAFKA_BROKER || 'localhost:9092']
});

const producer = kafka.producer({
  createPartitioner: Partitioners.LegacyPartitioner
});

const connectProducer = async () => {
  try {
    await producer.connect();
    console.log('[Sistema] Productor Kafka conectado exitosamente a la Capa de Enrutamiento.');
  } catch (error) {
    console.error('[Error] Falla en la conexión del productor Kafka:', error);
    process.exit(1);
  }
};

module.exports = { producer, connectProducer };