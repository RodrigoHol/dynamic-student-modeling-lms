const { producer } = require('../config/kafka.config.js');

const receiveLmsEvent = async (req, res) => {
  try {
    const rawEvent = req.body;

    if (!rawEvent || Object.keys(rawEvent).length === 0) {
      return res.status(400).json({ error: 'Carga útil (payload) ausente o inválida' });
    }
    await producer.send({
      topic: 'raw-lms-events',
      messages: [
        { 
          key: String(rawEvent.userid || 'anonymous'), 
          value: JSON.stringify(rawEvent) 
        }
      ],
    });

    return res.status(202).json({ status: 'Evento encolado exitosamente' });

  } catch (error) {
    console.error('[Error] Fallo al procesar el evento del LMS:', error);
    return res.status(500).json({ error: 'Error interno del Gateway de Ingestión' });
  }
};

module.exports = { receiveLmsEvent };