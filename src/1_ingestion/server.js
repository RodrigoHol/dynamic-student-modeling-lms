const express = require('express');
const { connectProducer } = require('./config/kafka.config.js');
const { receiveLmsEvent } = require('./controllers/webhook.controller.js');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware para parseo de JSON entrante
app.use(express.json());

app.post('/api/v1/webhook/moodle', receiveLmsEvent);

const startServer = async () => {
  await connectProducer();
  app.listen(PORT, () => {
    console.log(`[Sistema] Gateway de Ingestión operando en el puerto ${PORT}`);
    console.log(`[Sistema] Arquitectura Kappa: Listo para procesar flujos continuos.`);
  });
};

startServer();