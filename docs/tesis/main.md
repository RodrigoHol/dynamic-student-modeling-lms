  Facultad de Estadística e Informática Región Xalapa  Ingeniería en Sistemas y Tecnologías de la Información  Implementación y validación de la automatización del modelado dinámico e interpretable de patrones de interacción estudiantil en LMS.  Tesis para acreditar la Experiencia recepcional  Presenta: Rodrigo Hernández Holguín Director: Dr. Edgard Iván Benítez Guerrero    Julio de 2027  “Lis de Veracruz: Arte, Ciencia, Luz”    Universidad Veracruzana  Facultad de Estadística e Informática Región Xalapa  Ingeniería en Sistemas y Tecnologías de la Información  Implementación y validación de la automatización del modelado dinámico e interpretable de patrones de interacción estudiantil en LMS.  Tesis para acreditar la Experiencia recepcional  Presenta: Rodrigo Hernández Holguín  Director:  Dr. Edgard Iván Benítez Guerrero          Índice

I.

Introducción

I.1. Antecedentes

. .

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.2. Planteamiento del problema

. . . . . . . . . . . . . . . . . . . . . . . . . . .

I.3. Preguntas de investigación . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.4. Objetivos

.

.

.

. .

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.4.1. Objetivo General

. . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.4.2. Objetivos Específicos . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.5.

Justificación . .

.

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.6. Alcances y limitaciones . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.6.1. Alcances

.

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

I.6.2. Limitaciones

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

II. Marco teórico y estado del arte

II.1. Marco teórico . .

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

II.1.1. Modelado de estudiantes y de su comportamiento en línea . . . . . . .

II.1.2. Minería de Datos Educativos y Métodos de Generación de Modelos . .

II.1.3.

Infraestructura de datos y entornos virtuales de aprendizaje . . . . . . .

II.1.4. Ventanas de tiempo en el procesamiento de flujos de datos . . . . . . .

II.2. Estado del arte . .

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

II.2.1. Modelos de predicción en la Minería de Datos Educativos

. . . . . . .

II.2.2. Modelado dinámico y procesamiento en tiempo real

. . . . . . . . . .

II.2.3. Minería de procesos educativos e interpretabilidad algorítmica . . . . .

II.2.4. Conclusión . .

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

III.Diseño general de la propuesta de solución

III.1. Panorama general de la solución computacional

. . . . . . . . . . . . . . . . .

III.2. Modelo conceptual, naturaleza del flujo y persistencia de datos . . . . . . . . .

III.2.1. De los datos estáticos tradicionales al flujo continuo mediante ventanas

1

1

2

3

3

3

4

4

5

5

6

7

7

7

9

10

12

14

14

15

15

17

19

19

21

disjuntas

.

.

.

.

. . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

21

I

III.2.2. Registro canónico inmutable (Bitácora de adición)

. . . . . . . . . . .

III.2.3. Almacén de estado operativo y esquemas de representación . . . . . .

III.2.3.1. Esquema para perfiles dinámicos (Modelo semiestructurado)

III.2.3.2. Esquema para modelos de procesos (Modelo topológico basa-

22

23

23

do en grafos) . . . . . . . . . . . . . . . . . . . . . . . . . .

24

III.2.3.3. Esquema relacional para metadatos institucionales y configu-

ración . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

III.3. Estructuración funcional por capas . . . . . . . . . . . . . . . . . . . . . . . .

III.3.1. Capa de extracción e ingesta de datos . . . . . . . . . . . . . . . . . .

III.3.1.1. Dinámica funcional y flujo de datos en la ingesta . . . . . . .

III.3.2. Capa de análisis y procesamiento de datos . . . . . . . . . . . . . . . .

III.3.2.1. Preprocesamiento, consolidación y abstracción semántica . .

III.3.2.2. Modelado concurrente dual

. . . . . . . . . . . . . . . . . .

III.3.3. Capa de presentación e interpretabilidad . . . . . . . . . . . . . . . . .

III.3.3.1. Flujo y transformación hacia la interpretabilidad . . . . . . .

III.3.4. Resumen del capítulo . . . . . . . . . . . . . . . . . . . . . . . . . . .

24

24

25

25

26

26

27

28

28

28

II

Índice de figuras

II.1. Modelos conceptuales de ventanas de tiempo para la agregación sobre flujos

continuos de datos: (a) hito, (b) volcado o disjunta y (c) deslizante. Adaptado

conceptualmente de Gama Gama, 2010.

. . . . . . . . . . . . . . . . . . . . .

14

II.2. Ejemplo de la evolución temporal de perfiles estudiantiles mediante agrupamien-

to (clustering) en flujos de datos. Adaptado de Zavaleta-Sánchez et al. Zavaleta-Sanchez2025. 16

II.3. Representación interpretable del comportamiento estudiantil mediante un grafo

de secuencia de interacciones extraído con EPM. Adaptado de Zavaleta-Sánchez

et al. Zavaleta-Sanchez2025.

. . . . . . . . . . . . . . . . . . . . . . . . . .

17

III.1. Diagrama conceptual de la arquitectura unificada tipo Kappa para el modelado

dinámico e interpretable de interacciones en LMS. . . . . . . . . . . . . . . . .

20

III

Índice de tablas

II.1. Comparativa de los principales Sistemas de Gestión de Aprendizaje (LMS) como

fuentes de datos educativos.

. . . . . . . . . . . . . . . . . . . . . . . . . . .

11

IV

I. Introducción

I.1 Antecedentes

En los últimos años, los Sistemas de Gestión de Aprendizaje (LMS) han trascendido su

función inicial como simples repositorios de contenido para consolidarse como el núcleo ope-

rativo de la educación digital contemporánea Supriyanto et al., 2025; Zavaleta-Sanchez et al.,

2025. Estas plataformas ofrecen la capacidad técnica de registrar meticulosamente cada inter-

acción, clic y trayectoria de navegación de los estudiantes, generando volúmenes masivos de

datos asíncronos. La trascendencia de este fenómeno radica en que, al procesarse de manera es-

tructurada, esta información permite modelar perfiles estudiantiles basados directamente en su

comportamiento real dentro del entorno virtual Zavaleta-Sanchez et al., 2025. Esto ha motivado

a la comunidad investigadora e instituciones a desarrollar métodos para extraer valor de estos

registros continuos con el fin de personalizar la enseñanza, identificar riesgos de bajo rendimien-

to y evaluar la efectividad del diseño instruccional, consolidando a los LMS como un recurso

analítico primordial en el entorno educativo Mercado et al., 2024; Setiadi et al., 2025.

Para estructurar y analizar metodológicamente esta información, la literatura ha adopta-

do principalmente dos grandes paradigmas: la Minería de Datos Educativos (EDM) y la Minería

de Procesos Educativos (EPM) Semler et al., 2025. Por un lado, diversos estudios han aplica-

do técnicas predictivas y de aprendizaje automático propias de la EDM para evaluar y antici-

par el rendimiento académico a partir del historial de interacción del usuario Mercado et al.,

2024; Setiadi et al., 2025. Por otro lado, la EPM ha demostrado una notable eficacia al extraer

conocimiento de los registros de eventos (event logs) para descubrir, auditar y mapear visual-

mente las secuencias y rutas de aprendizaje empíricas en entornos asíncronos AlQaheri y Panda,

2022; Supriyanto et al., 2025. En conjunto, estas investigaciones validan la factibilidad técnica

de caracterizar el comportamiento en línea y aportan evidencia crucial para fundamentar mejoras

didácticas Semler et al., 2025.

Sin embargo, a pesar de estos sólidos avances, persiste una brecha tecnológica crítica que

restringe su adopción como una herramienta confiable para la gestión basada en evidencia. La

revisión sistemática de la literatura advierte que la mayoría de los esfuerzos actuales operan de

forma fragmentada y bajo un enfoque de análisis estático o por lotes (batch); es decir, construyen

1

perfiles retrospectivos que no se adaptan ni actualizan conforme evoluciona el comportamiento

del alumno durante su ciclo formativo Semler et al., 2025; Zavaleta-Sanchez et al., 2025. Ade-

más, una proporción significativa de estos modelos predictivos opera como sistemas opacos o

de “caja negra”, arrojando métricas sin proporcionar una justificación estructural que el profesor

pueda analizar o interpretar pedagógicamente Arrieta et al., 2020; Lee et al., 2025. Si bien exis-

ten marcos teóricos recientes que proponen la integración del procesamiento de flujos continuos

de datos con minería de procesos Zavaleta-Sanchez et al., 2025, aún no se ha consolidado una

plataforma de software unificada que automatice este ciclo analítico de principio a fin, capaz de

generar perfiles estudiantiles dinámicos, fundamentados en su interacción constante, y que ase-

guren una interpretabilidad algorítmica indispensable para orientar el diseño de intervenciones

pedagógicas oportunas.

I.2 Planteamiento del problema

La literatura reciente en Minería de Datos Educativos (EDM) y Minería de Procesos

Educativos (EPM) ha demostrado avances significativos en el análisis del comportamiento es-

tudiantil Semler et al., 2025; Supriyanto et al., 2025. Existen investigaciones consolidadas que

predicen el rendimiento del alumno o auditan su historial de navegación dentro de un LMS de

forma retrospectiva Mercado et al., 2024; Setiadi et al., 2025. Sin embargo, la limitación inhe-

rente a estos enfoques radica en la prevalencia del análisis tradicional basado en datos estáticos

por lotes; se carece de la integración de técnicas capaces de operar sobre flujos continuos de

eventos (data streams), donde el perfil computacional del estudiante se ajuste incremental y au-

tomáticamente conforme evolucionan sus interacciones en el LMS a lo largo del curso Batool y

Abbas, 2021; Zavaleta-Sanchez et al., 2025.

Por otro lado, para que el sector docente adopte estos sistemas analíticos, es indispensable

garantizar su transparencia y usabilidad operativa Arrieta et al., 2020. Aunque existen marcos

teóricos sólidos orientados a la creación de modelos dinámicos Zavaleta-Sanchez et al., 2025, o

aproximaciones que recurren a la Inteligencia Artificial Explicable (XAI) para interpretar predic-

ciones estáticas Desai, 2025; Lee et al., 2025, aún no se ha construido una plataforma de software

unificada que automatice este proceso analítico de principio a fin. Específicamente, el desafío

pendiente en la literatura científica consiste en generar perfiles estudiantiles computacionalmen-

te dinámicos que el educador pueda interpretar con facilidad y sin ambigüedad estructural, aun

2

cuando dichos perfiles cambien y se actualicen continuamente a partir de eventos capturados en

tiempo real.

I.3 Preguntas de investigación

Para abordar la problemática planteada, esta investigación se guía por los siguientes cues-

tionamientos:

¿En qué medida la automatización concurrente de la minería de flujos de datos y la minería

de procesos logra mantener tiempos de procesamiento de baja latencia ante el volumen

masivo de eventos asíncronos generados en un LMS?

¿Cuál es el grado de interpretabilidad y utilidad práctica que ofrecen los perfiles de usuario

estructurados a partir de rutas secuenciales continuas, al ser expuestos a la evaluación o

criterios de toma de decisiones docentes?

¿Cuáles son las diferencias operativas y de fidelidad representativa al contrastar el mode-

lado del comportamiento estudiantil basado en un paradigma de análisis estático por lotes

(batch) frente a la minería de flujos de datos continuos (data streams)?

I.4 Objetivos

La definición de objetivos de investigación fundamenta el alcance metodológico y la

dirección técnica de este proyecto. Considerando la complejidad de procesar y extraer valor de

los flujos continuos de información generados en los Sistemas de Gestión de Aprendizaje (LMS),

resulta indispensable trazar metas precisas que guíen la transición de los fundamentos teóricos

hacia una plataforma computacional aplicable. A continuación, se expone el objetivo general, el

cual rige el propósito central de este trabajo, y los objetivos específicos que delinean las etapas

arquitectónicas, analíticas y de validación necesarias para su implementación.

I.4.1 Objetivo General

Automatizar el perfilado dinámico de estudiantes a partir de sus interacciones en un LMS,

mediante la puesta en operación de una plataforma de software que implemente un método ba-

sado en minería de flujos de datos y de procesos, para obtener perfiles educativos interpretables,

consistentes y reproducibles.

3

I.4.2 Objetivos Específicos

Diseñar la arquitectura de datos para la extracción, limpieza y estructuración continua de

los registros de interacción provenientes del LMS.

Desarrollar el módulo analítico que integre y ejecute coordinadamente los algoritmos de

minería de flujos de datos y minería de procesos para generar los modelos dinámicos de

usuario.

Evaluar el desempeño de la plataforma computacional midiendo su eficiencia en el tiempo

de procesamiento, la consistencia algorítmica, la reproducibilidad del método y la inter-

pretabilidad de los perfiles resultantes.

I.5 Justificación

La analítica del aprendizaje en los Sistemas de Gestión de Aprendizaje (LMS) ha avanza-

do primordialmente en la predicción retrospectiva y el análisis de datos estáticos Mercado et al.,

2024; Setiadi et al., 2025. Sin embargo, existe un vacío tecnológico sustancial en la integración

de técnicas que procesen flujos continuos de eventos para ajustar automáticamente los perfiles

computacionales conforme evolucionan las interacciones del estudiante Zavaleta-Sanchez et al.,

2025. Atender este problema resulta fundamental, ya que la literatura advierte que los esfuerzos

analíticos actuales suelen generar predicciones estáticas que operan como sistemas opacos, es

decir, modelos de “caja negra” cuyo funcionamiento interno carece de la capacidad de ser expli-

cado o presentado en términos comprensibles para el ser humano Arrieta et al., 2020; Lee et al.,

2025. En consecuencia, para que estas herramientas logren una verdadera adopción en el sec-

tor docente, es indispensable garantizar su usabilidad e interpretabilidad computacional frente a

flujos de datos dinámicos Desai, 2025; Lee et al., 2025.

Ante esta necesidad, la presente investigación aportará evidencia y la sistematización

técnica para operar una plataforma computacional unificada que automatice el método de mo-

delado dinámico de extremo a extremo. Este desarrollo contribuirá a superar la fragmentación

detectada en la literatura de minería de procesos educativos Semler et al., 2025 y a consolidar la

convergencia metodológica entre la minería de flujos de datos y la minería de procesos Zavaleta-

Sanchez et al., 2025, garantizando un tiempo de procesamiento eficiente y la reproducibilidad

algorítmica. Los principales beneficiarios serán los educadores, a quienes el sistema ofrecerá

4

criterios para la toma de decisiones pedagógicas basadas en evidencia confiable. De este modo,

la automatización analítica permitirá identificar patrones tempranos y rutas de aprendizaje reales

mediante perfiles dinámicos, estructurados y directamente comprensibles para el usuario final.

La ejecución de este proyecto es técnica y metodológicamente viable gracias a la exis-

tencia de fundamentos teóricos sólidos que fungen como núcleo estructurado para la automati-

zación, tales como los marcos recientes que integran la minería de flujos y procesos en contextos

educativos Zavaleta-Sanchez et al., 2025. Lejos de partir de un enfoque especulativo, la pro-

puesta materializará en software una estructura teórica formal. Adicionalmente, la viabilidad

algorítmica y de infraestructura está respaldada por trabajos afines que demuestran la eficacia

de las arquitecturas orientadas a eventos en tiempo real Kundavaram, 2025 y el agrupamiento

evolutivo sobre flujos continuos de datos Batool y Abbas, 2021. La articulación de estas bases

comprobadas brindará el rigor necesario para garantizar que la transición del paradigma estático

al dinámico sea consistente y validable empíricamente.

I.6 Alcances y limitaciones

En esta sección se establecen las fronteras operativas y conceptuales de la investigación.

A continuación, se delimita el alcance del desarrollo tecnológico de la plataforma y se expli-

citan las restricciones inherentes al procesamiento de datos asíncronos generados dentro de los

Sistemas de Gestión de Aprendizaje (LMS).

I.6.1 Alcances

El alcance principal de este proyecto comprende la sistematización técnica y automa-

tización metodológica del modelado dinámico de usuarios. Específicamente, la investigación

abarcará las siguientes metas operativas:

Desarrollo de la infraestructura de datos: Se diseñará e implementará una arquitectura

orientada al procesamiento de flujos continuos (arquitectura tipo Kappa) para automatizar

la extracción, limpieza y estructuración de los registros de interacción de los estudiantes

desde el LMS Kundavaram, 2025.

Integración del módulo analítico: Se construirá un sistema unificado de software que eje-

cute, de forma coordinada, algoritmos de agrupamiento de minería de flujos de datos Batool

y Abbas, 2021 junto con técnicas de minería de procesos AlQaheri y Panda, 2022; Supri-

5

yanto et al., 2025 para generar rutas de aprendizaje y perfiles estudiantiles que evolucionen

en el tiempo Zavaleta-Sanchez et al., 2025.

Validación computacional: El desempeño de la plataforma será evaluado utilizando mé-

tricas técnicas de eficiencia, midiendo la latencia en el tiempo de procesamiento de eventos

y garantizando la reproducibilidad algorítmica del método.

Evaluación de transparencia: Se validará el grado de interpretabilidad de los perfiles

resultantes, asegurando que el modelo exponga justificaciones estructurales comprensibles

orientadas a la toma de decisiones docentes Arrieta et al., 2020; Lee et al., 2025.

I.6.2 Limitaciones

Aunque la plataforma automatizará el análisis de datos en tiempo real, el desarrollo y

ejecución del proyecto están sujetos a restricciones técnicas y de frontera que deben considerarse:

Dependencia de los registros del LMS (Logs): El sistema de modelado funciona estricta-

mente a partir de los datos que la plataforma educativa logra registrar y almacenar Setiadi

et al., 2025. Si el LMS no captura ciertas interacciones o secuencias de navegación de

los estudiantes debido a limitaciones de instrumentación técnica, el algoritmo no tendrá

manera de procesarlas ni de incluirlas en el perfil dinámico.

Frontera técnica vs. pedagógica: El proyecto está enfocado en la ciencia de datos y la in-

geniería de software para construir y validar la plataforma tecnológica. El sistema entregará

los perfiles interpretables a los profesores como una herramienta de apoyo analítico, pero

la investigación no evaluará experimentalmente el impacto directo de las intervenciones

didácticas que los docentes implementen en el rendimiento final de los alumnos.

Prioridad en la interpretabilidad sobre predicciones puras: Existen modelos predicti-

vos de caja negra que alcanzan altos coeficientes de precisión matemática pero carecen de

transparencia operativa Arrieta et al., 2020; Lee et al., 2025. Esta investigación se limita

deliberadamente a la generación de modelos descriptivos, transparentes y estructurados en

rutas de procesos; no se desarrollarán arquitecturas de aprendizaje profundo complejas si

estas comprometen la interpretabilidad directa requerida por el educador.

6

II. Marco teórico y estado del arte

II.1 Marco teórico

El presente capítulo establece los fundamentos conceptuales, metodológicos y tecnoló-

gicos que sustentan el diseño e implementación de sistemas automatizados para el análisis del

comportamiento estudiantil en entornos digitales. Con el propósito de abordar el fenómeno de

estudio bajo una estructura deductiva —partiendo de lo general hacia lo particular—, la revisión

de la literatura se organiza en tres ejes temáticos. En primera instancia, se examina el paradigma

del modelado de usuarios y su especialización en el ámbito educativo, trazando su evolución

desde los esquemas estáticos tradicionales hacia el modelado dinámico e interpretable basado en

flujos continuos de información. En segundo lugar, se abordan los métodos analíticos que hacen

posible la construcción de dichos perfiles, profundizando en la Minería de Datos Educativos, el

agrupamiento incremental sobre flujos de datos y la Minería de Procesos Educativos. Finalmen-

te, se describe el soporte de infraestructura necesario para operar estos modelos, contemplando

las fuentes de información institucionales —con énfasis en los Sistemas de Gestión de Apren-

dizaje (LMS, por sus siglas en inglés)—, el proceso técnico de consolidación de conjuntos de

datos y las arquitecturas de software orientadas a eventos.

II.1.1 Modelado de estudiantes y de su comportamiento en línea

En el dominio de la analítica del aprendizaje y los entornos educativos adaptativos, el

modelado de estudiantes (Student Modeling) se define como el proceso de construir y actuali-

zar una representación computacional explícita de las características de un alumno, tales como

su nivel de dominio cognitivo, preferencias de estudio y patrones conductuales de interacción

Brusilovsky y Millán, 2007; Chrysafiadi y Virvou, 2013. El objetivo principal de este perfilado

consiste en permitir que plataformas como los Sistemas de Gestión de Aprendizaje (LMS) adap-

ten los recursos y las intervenciones pedagógicas a las necesidades particulares de cada individuo

durante su trayecto formativo Chrysafiadi y Virvou, 2013; Fischer, 2001.

Históricamente, la recolección de evidencia para conformar estos perfiles estudiantiles ha

transitado por mecanismos estáticos de naturaleza explícita e implícita Abyaa et al., 2019; Bru-

silovsky y Millán, 2007. Los métodos explícitos requieren la intervención directa del estudiante

7

a través de cuestionarios diagnósticos aplicados al inicio del curso; no obstante, este esquema

presenta sesgos de autopercepción y carece de sensibilidad ante la evolución que experimenta el

alumno. Como alternativa, la incorporación de técnicas de Minería de Datos Educativos (EDM)

ha permitido inferir perfiles de manera implícita mediante el análisis retrospectivo de los historia-

les de interacción acumulados Chrysafiadi y Virvou, 2013. Sin embargo, la literatura advierte que

estos modelos operan mayoritariamente bajo un paradigma estático o por lotes (batch), asumien-

do erróneamente que la conducta del estudiante permanece invariable o evaluándola únicamente

cuando el periodo escolar ha concluido Zahoor y Sofi, 2025.

Dado que el aprendizaje constituye un proceso cognitivo en constante transformación,

donde las estrategias de estudio y las rutas de navegación se ajustan frente a la dificultad de

los temas, las representaciones estáticas resultan insuficientes para un seguimiento académico

oportuno Abyaa et al., 2019; Zahoor y Sofi, 2025. Esta limitación ha impulsado el desarrollo

del modelado dinámico de estudiantes (Dynamic Student Modeling), el cual concibe al perfil

computacional como una estructura viva que se recalibra continuamente conforme ingresan nue-

vos registros de actividad asíncrona en el LMS. Para sostener esta actualización ininterrumpida

sin incurrir en un reprocesamiento exhaustivo, este paradigma se apoya en la minería de flujos de

datos (Data Stream Mining), procesando la información de manera incremental Gama, 2010. En

esta línea, Zavaleta-Sánchez et al. Zavaleta-Sanchez et al., 2025 proponen un marco metodoló-

gico que articula la minería de flujos de datos con el descubrimiento de procesos educativos para

modelar la evolución temporal del alumno; en la presente investigación, dicha estructura teórica

constituye el núcleo metodológico que se busca automatizar a nivel de ingeniería de software.

Adicionalmente, para que el perfilado dinámico sea adoptado de manera efectiva por la

comunidad docente, resulta imperativo evitar sistemas opacos. En el ámbito del aprendizaje au-

tomático, la interpretabilidad se define como la capacidad de explicar el funcionamiento interno

de un modelo computacional en términos comprensibles para el ser humano Arrieta et al., 2020.

Aplicado al entorno educativo, Lee et al. Lee et al., 2025 sostienen que los sistemas analíticos

deben priorizar la transparencia algorítmica. Dentro del presente proyecto, la interpretabilidad

constituye un requisito transversal para generar perfiles estudiantiles legibles, cuyas trayectorias

de interacción evidencien claramente el porqué de cada actualización o agrupamiento, dotando

a los educadores de evidencia empírica rastreable para fundamentar el diseño de intervenciones

pedagógicas oportunas.

8

II.1.2 Minería de Datos Educativos y Métodos de Generación de Modelos

En el contexto de los entornos educativos digitales, la extracción algorítmica de valor a

partir de los volúmenes masivos de datos asíncronos generados recae en la Minería de Datos

Educativos (Educational Data Mining, EDM) Romero y Ventura, 2020. Esta disciplina propor-

ciona la estructura metodológica para descubrir patrones sistemáticos de interacción y evaluar

el desempeño de los estudiantes mediante técnicas computacionales. Investigaciones recientes,

como las de Mercado et al. Mercado et al., 2024, demuestran empíricamente que la aplicación

de métodos predictivos de EDM sobre los historiales de navegación permite identificar patro-


nes conductuales tempranos que correlacionan de manera directa con el rendimiento final del

alumno.

Para materializar este descubrimiento de patrones y construir computacionalmente los

perfiles estudiantiles, la literatura distingue dos métodos fundamentales para la recuperación de

datos: el enfoque explícito (manual) y el modelado implícito. El modelado explícito requiere

la intervención directa del estudiante o del docente para recopilar información, típicamente a

través de cuestionarios o evaluaciones diagnósticas previas. Si bien este mecanismo establece

una línea base, resulta estático y propenso a sesgos de autopercepción, ya que no logra capturar

la evolución continua del estudiante frente a la dificultad del curso ni refleja su comportamiento

empírico real dentro de la plataforma.

En contraste, el modelado implícito automatiza la recuperación de datos extrayendo cono-

cimiento de manera directa desde los registros de eventos (logs) del LMS Supriyanto et al., 2025.

Este enfoque permite que disciplinas complementarias, como la Minería de Procesos Educativos

(EPM), auditen y mapeen visualmente las secuencias y rutas de aprendizaje reales en entornos

asíncronos AlQaheri y Panda, 2022. No obstante, la evidencia advierte que una gran proporción

de los esfuerzos de modelado implícito actuales persisten en operar bajo un paradigma de análisis

estático o por lotes (batch) Setiadi et al., 2025. En consecuencia, construyen perfiles retrospecti-

vos que no se adaptan ni actualizan incrementalmente conforme el comportamiento del alumno

evoluciona durante el ciclo formativo.

Para superar las limitaciones retrospectivas del modelado implícito tradicional, resulta

imperativa la transición hacia un modelado dinámico impulsado por la minería de flujos de datos

(Data Stream Mining) y el procesamiento basado en eventos (event-driven) Zavaleta-Sanchez2025;

Kundavaram, 2025. Esta ingesta continua permite que técnicas de aprendizaje no supervisado,

9

como el agrupamiento (clustering) evolutivo, ajusten sus distribuciones incrementales en tiem-

po real Batool y Abbas, 2021. Finalmente, para que esta automatización implícita posea utilidad

práctica, debe regirse bajo el principio de interpretabilidad algorítmica Lee et al., 2025. Evitando

los sistemas opacos o de çaja negra”Arrieta2020, el modelado dinámico debe proporcionar una

justificación estructural clara, dotando a los educadores de evidencia empírica y rastreable para

fundamentar el diseño de intervenciones pedagógicas oportunas Desai, 2025.

II.1.3 Infraestructura de datos y entornos virtuales de aprendizaje

La operación continua de los métodos analíticos descritos requiere de una infraestructura

tecnológica capaz de proveer flujos de datos íntegros y estructurados. En el ecosistema digital de

las instituciones educativas coexisten múltiples fuentes de información, entre las que figuran los

Sistemas de Información Estudiantil (Student Information Systems, SIS) orientados a la gestión

de matrículas, historiales académicos y trámites administrativos, los repositorios digitales y los

sistemas de gestión bibliotecaria Turnbull et al., 2020. Sin embargo, mientras que los sistemas

administrativos almacenan datos demográficos o calificaciones sumativas de baja frecuencia de

actualización, el estudio del comportamiento de aprendizaje demanda fuentes que capturen la

actividad cotidiana del alumno. Por esta razón, la fuente de datos primordial para este proyecto

son los Sistemas de Gestión de Aprendizaje (LMS).

Un LMS se define como una plataforma de software basada en tecnologías web diseñada

para planificar, distribuir, evaluar y gestionar procesos de enseñanza-aprendizaje, registrando de

manera sistemática las interacciones entre estudiantes, docentes y recursos didácticos Turnbull et

al., 2020. En el mercado e industria del software educativo existen diversas alternativas de LMS

cuyas arquitecturas determinan el grado de detalle y accesibilidad de las bitácoras generadas. En

la Tabla II.1 se presenta una comparativa técnica de los principales LMS empleados en el ámbito

académico.

Como se aprecia en la Tabla II.1, entornos de código abierto como Moodle sobresalen en

proyectos de minería educativa debido a la transparencia de su esquema relacional y a la riqueza

de sus tablas de bitácoras, donde cada clic queda asociado a un usuario, un módulo pedagógico y

un instante preciso Romero y Ventura, 2020; Supriyanto et al., 2025. Pese a ello, los datos crudos

generados por cualquier LMS presentan un nivel de granularidad excesivamente bajo, además

de registros administrativos irrelevantes o eventos redundantes que impiden su consumo directo

10

Tabla II.1. Comparativa de los principales Sistemas de Gestión de Aprendizaje (LMS) como fuentes de
datos educativos.

Enfoque principal

Registro de interacciones
(Logs)

Facilidad de extracción
analítica

Plataforma
LMS

Moodle

Esquema de licen-
cia

Código
(GPL)

abierto

Educación superior y di-
seño constructivista mo-
dular

Canvas

Código
abierto
(AGPLv3) / Comer-
cial en la nube

Educación superior e in-
teroperabilidad en la nube

Blackboard
Learn

Propietario / Comer-
cial

Gestión académica insti-
tucional a gran escala

Bitácoras relacionales deta-
lladas a nivel de evento, com-
ponente, acción y marca tem-
poral

Eventos de navegación y ac-
tividad capturados mediante
servicios de telemetría (Can-
vas Data)

Registros de auditoría de se-
siones, entregas y acceso a
contenidos

Alta (acceso directo a base
de datos, servicios web y ex-
portación nativa)

Media-Alta (requiere con-
sumo de APIs REST o ex-
portación de flujos de datos)

Media (acceso restringido
por arquitectura propietaria;
depende de APIs institucio-
nales)

Open edX

Código
(AGPL)

abier-
abierto

Cursos masivos
tos en línea (MOOC)
y aprendizaje a ritmo
propio

Eventos de seguimiento en
formato JSON generados por
interacciones en video y eva-
luaciones

Alta (orientado a eventos,
aunque requiere infraestruc-
tura compleja de desplie-
gue)

Google Class-
room

Propietario
mium)

(Free-

Educación básica, media
y gestión ágil de tareas

Registros básicos de entrega
de asignaciones y publicacio-
nes en el tablón

Chamilo

Código
(GPLv3)

abierto

presencial
Educación
apoyada en TIC y capa-
citación

Reportes de seguimiento de
lecciones, tiempos de cone-
xión y evaluaciones

Baja (trazas de navegación
limitadas; extracción sujeta
a APIs de Google Workspa-
ce)

Media-Alta (acceso a base
de datos relacional con me-
nor granularidad de eventos
que Moodle)

11

por parte de los algoritmos de aprendizaje automático Bogarín et al., 2018.

Para resolver esta brecha técnica resulta indispensable la consolidación del conjunto

de datos (Dataset Consolidation), proceso que comprende la extracción, limpieza, integración,

transformación de formato y abstracción semántica de las trazas crudas para estructurarlas en ma-

trices de características y registros de eventos coherentes Bogarín et al., 2018; Romero y Ventura,

2020. Dentro de este flujo de preprocesamiento, además de filtrar el ruido y estandarizar las mar-

cas de tiempo, resulta fundamental reducir la variabilidad de acciones técnicas agrupándolas en

categorías pedagógicas significativas denominadas Eventos de Alto Nivel (High-Level Events)

en el marco de Zavaleta-Sánchez et al. Zavaleta-Sanchez et al., 2025, lo que permite condensar

las interacciones por estudiante y ventana temporal antes de su ingreso a los módulos de minería.

Finalmente, para que la recolección y consolidación de estos datos deje de ser una tarea

artesanal dependiente de exportaciones manuales, la infraestructura debe sustentarse en el pro-

cesamiento de datos basado en eventos (event-driven). Este paradigma de ingeniería de software

e ingeniería de datos se centra en la captura, transformación y despacho asíncrono de registros

en el momento en que se produce un cambio de estado o una acción en la plataforma origen.

De acuerdo con Kundavaram Kundavaram, 2025, la implementación de tuberías de datos (data

pipelines) orientadas a eventos permite automatizar la ingesta y el preprocesamiento de flujos

continuos con baja latencia y alta tolerancia a fallos. En el contexto de esta investigación, dicha

infraestructura representa el eslabón técnico encargado de acoplar el LMS con los algoritmos de

minería de flujos y de procesos, habilitando la actualización automática de los modelos estudian-

tiles.

II.1.4 Ventanas de tiempo en el procesamiento de flujos de datos

A diferencia de los conjuntos de datos estáticos almacenados en repositorios finitos, en

el ámbito de la minería de flujos de datos (Data Stream Mining) un flujo continuo se caracteriza

por ser potencialmente infinito, no estacionario y arribar de manera secuencial a tasas varia-

bles Gama, 2010. En este escenario, resulta computacionalmente inviable y metodológicamente

inadecuado acumular de forma indefinida la totalidad de la historia transaccional para calcular

métricas de actividad, dado que el comportamiento antiguo diluye la detección de patrones emer-

gentes y dificulta la identificación del cambio conceptual (concept drift) Batool y Abbas, 2021;

Gama, 2010.

12

Para acotar el análisis sobre flujos continuos, la literatura recurre a la abstracción de ven-

tanas de tiempo (time windows) Gama, 2010. Una ventana de tiempo constituye un operador

que delimita un subconjunto finito y temporalmente acotado de eventos dentro del flujo continuo

con el propósito de ejecutar agregaciones cuantitativas sobre un intervalo de interés. Formalmen-

te, dado un flujo de eventos S = {e1, e2, . . . , ek} ordenados cronológicamente por su estampa

temporal t(ei), una ventana de tiempo de amplitud ∆t evaluada en el instante t se define como:

W (t) = {ei ∈ S | (t − ∆t) < t(ei) ≤ t}

(II.1)

De acuerdo con Gama Gama, 2010, en la ingeniería de flujos de datos se distinguen

principalmente tres modelos conceptuales de ventanas:

1. Ventanas de hito (Landmark Windows): Fijan un punto de inicio temporal t0 inamovible

(por ejemplo, el inicio de un ciclo escolar) y acumulan todos los eventos hasta el instan-

te actual t, evaluando el intervalo [t0, t]. Si bien preservan la historia completa, su costo

computacional crece con el tiempo y presentan una alta inercia frente a cambios recientes

de comportamiento.

2. Ventanas de volcado o disjuntas (Tumbling Windows): Particionan el flujo continuo en

bloques temporales adyacentes de longitud fija ∆t que no se solapan entre sí (por ejemplo,

intervalos diarios o semanales). Al concluir cada intervalo, los datos contenidos se procesan

y la ventana se reinicia para capturar el bloque subsecuente.

3. Ventanas deslizantes (Sliding Windows): Mantienen una amplitud temporal fija ∆t, pero

se desplazan a lo largo del eje temporal conforme avanza un paso de deslizamiento δ,

donde δ ≤ ∆t. A medida que ingresan nuevos eventos en el instante t, los registros cuya

antigüedad supera el límite inferior (t − ∆t) son descartados bajo una política de primero

en entrar, primero en salir (FIFO).

En la Figura II.1 se esquematiza la operación de estos tres modelos de ventanas de tiempo

sobre un flujo continuo de eventos.

13

(a) Ventana de Hito (Landmark Window)

W3 = [t0, t3] (Acumulación continua desde el origen)

W2 = [t0, t2]

W1 = [t0, t1]

t0

t1

t2

Tiempo (t)
t3

(b) Ventana de Volcado / Disjunta (Tumbling Window)

Intervalos adyacentes de tamaño fijo ∆t sin solapamiento

W1 (∆t)

W2 (∆t)

W3 (∆t)

t0

t1

t2

t3

Tiempo (t)

(c) Ventana Deslizante (Sliding Window)

W (t + 2δ) [Descarte FIFO de eventos antiguos]

W (t + δ) [Desplazamiento δ]

W (t) [Amplitud ∆t]

Paso δ

t

t + δ

t + 2δ

Tiempo (t)

Figura II.1. Modelos conceptuales de ventanas de tiempo para la agregación sobre flujos continuos de
datos: (a) hito, (b) volcado o disjunta y (c) deslizante. Adaptado conceptualmente de Gama Gama, 2010.

II.2 Estado del arte

Para fundamentar la necesidad y viabilidad de este proyecto, se realizó una revisión de la

literatura en bases de datos de alto impacto, como IEEE Xplore, ScienceDirect, SpringerLink y

Google Académico. Con el propósito de capturar de manera exhaustiva las intersecciones entre

las plataformas educativas, la evolución de los perfiles de usuario y las técnicas analíticas avan-

zadas, la búsqueda se estructuró mediante la siguiente cadena de consulta ampliada: ("Learning

Management System.OR "LMS.OR .e-learning.OR .educational") AND (üser modeling.OR

"student modeling.OR "student behavior.OR "learning analytics") AND ("data stream

mining.OR "process mining.OR .educational data mining"). A partir de los resultados

obtenidos, los trabajos relacionados se han clasificado en tres ejes temáticos progresivos para

contrastar los problemas abordados, los métodos aplicados y su relación con la automatización

del modelado estudiantil.

II.2.1 Modelos de predicción en la Minería de Datos Educativos

Una vertiente predominante en la literatura es el uso de la Minería de Datos Educativos

(EDM) para evaluar y predecir el rendimiento académico. Investigaciones como la de Mercado

et al. Mercado et al., 2024 abordan la predicción oportuna en cursos de ritmo propio aplicando

técnicas predictivas sobre los historiales de navegación, logrando identificar patrones tempranos

14

que correlacionan fuertemente con el desempeño final. De manera convergente, autores como

Setiadi et al. Setiadi et al., 2025 subrayan que el ruido inherente a los datos de los LMS exige

una rigurosa selección de características para optimizar la precisión algorítmica.

Aunque estos enfoques ilustran el potencial de la analítica para adaptar los sistemas a

las necesidades del estudiante, presentan una limitación tecnológica estructural: operan bajo un

paradigma de análisis por lotes (batch). Estas propuestas generan predicciones estáticas que eva-

lúan al alumno de manera retrospectiva, sin la capacidad de actualizarse continuamente a medida

que el comportamiento y las estrategias de aprendizaje evolucionan a lo largo del curso.

II.2.2 Modelado dinámico y procesamiento en tiempo real

La necesidad de superar la naturaleza estática de los perfiles retrospectivos ha impulsado

enfoques técnicos orientados a la alta disponibilidad y el procesamiento de flujos. Kundavaram

Kundavaram, 2025 aborda la dificultad de procesar volúmenes masivos de información propo-

niendo una arquitectura de ingeniería de datos basada en eventos (event-driven), logrando la

ingesta de datos asíncronos en tiempo real.

Paralelamente, desde la perspectiva algorítmica, Zavaleta-Sánchez et al. Zavaleta-Sanchez2025

proponen un marco teórico que integra la minería de flujos de datos (Data Stream Mining) con

la minería de procesos para generar modelos que representen verdaderamente la evolución tem-

poral del estudiante. El agrupamiento evolutivo (stream clustering) dentro de este paradigma

permite segmentar a los usuarios en tiempo real conforme sus niveles de interacción cambian

(véase la Figura II.2). Si bien el enfoque de infraestructura de Kundavaram Kundavaram, 2025

resuelve la latencia, carece de un enfoque pedagógico; por el contrario, la articulación teórica de

Zavaleta-Sánchez et al. Zavaleta-Sanchez2025 constituye la base metodológica que la presente

investigación busca automatizar en una plataforma de software.

II.2.3 Minería de procesos educativos e interpretabilidad algorítmica

Para que las herramientas analíticas dinámicas superen la fase de experimentación y sean

adoptadas por la comunidad docente, la precisión computacional debe acompañarse de una es-

tricta transparencia. Investigaciones en Inteligencia Artificial Explicable (XAI) advierten que la

opacidad de los modelos predictivos de çaja negraïnhibe su utilidad pedagógica Desai, 2025; Lee

et al., 2025. Si bien algoritmos tradicionales como los árboles de decisión ofrecen un grado nativo

15

Figura II.2. Ejemplo de la evolución temporal de perfiles estudiantiles mediante agrupamiento
(clustering) en flujos de datos. Adaptado de Zavaleta-Sánchez et al. Zavaleta-Sanchez2025.

16

de interpretabilidad mediante reglas lógicas, resultan insuficientes para representar visualmente

la naturaleza causal y secuencial del comportamiento humano en un LMS.

Es en este punto donde la Minería de Procesos Educativos (EPM) se integra no solo como

técnica de descubrimiento, sino como el motor de explicabilidad del modelo AlQaheri y Panda,

2022; Supriyanto et al., 2025. Al aplicar técnicas de EPM directamente sobre los subgrupos

(clústeres) generados en la fase dinámica, es posible extraer conocimiento empírico sobre cómo

interactúa secuencialmente cada perfil. Esto produce grafos de flujo directo (Directly-Follows

Graphs) que permiten a los educadores visualizar con exactitud qué acciones precedieron a otras,

facilitando la comprensión del comportamiento cognitivo del alumno (véase la Figura II.3).

En consecuencia, el método propuesto en esta investigación genera dos salidas analíticas

altamente interpretables: 1) el modelo del estudiante, definido por su estado o clúster actual, y

2) el grafo de secuencia de interacciones, que justifica empíricamente dicho estado trazando la

ruta de aprendizaje real ejecutada en la plataforma.

Figura II.3. Representación interpretable del comportamiento estudiantil mediante un grafo de
secuencia de interacciones extraído con EPM. Adaptado de Zavaleta-Sánchez et al.
Zavaleta-Sanchez2025.

II.2.4 Conclusión

A partir de la revisión de la literatura, se evidencia un vacío crítico: la mayoría de los

trabajos resuelven problemas aislados, como la predicción estática algorítmica, la gestión pura

17

de infraestructura o el descubrimiento de procesos retrospectivos. A pesar de la existencia de

marcos teóricos robustos como el de Zavaleta-Sánchez et al. Zavaleta-Sanchez2025, no existe

una plataforma de software unificada que automatice este ciclo analítico de extremo a extremo.

Este proyecto cubre dicha brecha sistematizando la transición desde la ingesta de eventos hasta

la generación de las dos salidas interpretables , garantizando el soporte necesario para la toma

de decisiones docentes.

18

III. Diseño general de la propuesta de solución

En este capítulo se formaliza la concepción arquitectónica y funcional del sistema di-

señado para automatizar el modelado dinámico e interpretable del comportamiento estudiantil

en entornos virtuales de aprendizaje. Conforme a los principios de abstracción en la ingeniería

de software y la analítica de datos, este apartado se enfoca estrictamente en la definición con-

ceptual de los componentes, el tratamiento de los datos y los flujos de información del sistema,

delimitando las capacidades operativas requeridas sin condicionar la propuesta a tecnologías o

herramientas de implementación específicas, las cuales serán detalladas en el capítulo subsi-

guiente.

III.1 Panorama general de la solución computacional

La construcción de una solución computacional destinada a analizar de manera continua

los eventos de interacción en un Sistema de Gestión de Aprendizaje (LMS) exige trascender las

limitaciones impuestas por los paradigmas de procesamiento dual tradicionales. Comúnmente,

las arquitecturas analíticas convencionales recurren a bifurcaciones funcionales donde una capa

procesa eventos en línea para métricas transitorias, mientras que una capa paralela recomputa pe-

riódicamente la totalidad del historial mediante procesamiento por lotes (batch). En un contexto

educativo, este desacoplamiento introduce una divergencia representativa crítica: el perfil del es-

tudiante queda desfasado respecto a su trayectoria real o demanda un costo de reprocesamiento

temporal elevado.

Frente a este desafío, la solución computacional propuesta se presenta en la Figura III.1,

la cual adopta una arquitectura unificada de tipo Kappa. Este paradigma se sustenta en un prin-

cipio de diseño central: tratar la totalidad de los datos —tanto las interacciones pasadas como

las que suceden en el presente— bajo una única abstracción canónica constituida por un flujo

continuo, ordenado e inmutable de eventos. Al suprimir la separación entre cómputo en línea

y cómputo por lotes, el sistema procesa la información entrante mediante una tubería analítica

unificada, habilitando que el perfil conductual del estudiante evolucione de manera incremental

y consistente.

19

Figura III.1. Diagrama conceptual de la arquitectura unificada tipo Kappa para el modelado dinámico e
interpretable de interacciones en LMS.

Como se observa en la Figura III.1, la arquitectura se articula en cuatro capas funcionales

interconectadas de manera asíncrona:

1. Telemetría e ingesta continua: Constituye el punto de entrada de la plataforma. Su función

es capturar de forma no bloqueante cada acción generada por el estudiante en el LMS,

normalizarla en un formato canónico y depositarla en un registro continuo inmutable de

sólo adición (append-only log), el cual funge como fuente de verdad histórica.

2. Transformación y analítica dual concurrente: Consume el flujo desde el registro inmu-

table para ejecutar el preprocesamiento y la abstracción semántica hacia Eventos de Alto

Nivel. A partir de esta consolidación, bifurca el flujo hacia dos procesos analíticos coor-

dinados: el agrupamiento evolutivo sobre flujos de datos (Data Stream Clustering) y el

descubrimiento de rutas secuenciales mediante Minería de Procesos Educativos (Educa-

tional Process Mining).

3. Persistencia de estado operativo: Almacena de manera desacoplada las representaciones

actualizadas producidas por la capa analítica, manteniendo tanto los perfiles dinámicos es-

tudiantiles bajo un esquema semiestructurado como las topologías de procesos descubiertas

bajo un esquema basado en grafos.

4. Mediación e interpretabilidad: Proyecta los modelos matemáticos y estructurales res-

guardados en el estado operativo hacia representaciones visuales comprensibles para el

docente, evitando la opacidad de los sistemas de “caja negra” y proveyendo evidencia em-

pírica rastreable para el seguimiento académico.

20

I. Telemetría e Ingesta ContinuaII. Transformación y Analítica Dual ConcurrenteIII. Persistencia de Estado OperativoIV. Mediación e InterpretabilidadEntorno Virtual (LMS)[Acciones del Estudiante]Telemetría y CapturaOrientada a EventosRegistro Continuo Inmutable(Log de sólo adición / Append-Only)[Fuente de Verdad Histórica]Preprocesamiento y AbstracciónSemántica (Eventos de Alto Nivel)Agrupamiento Evolutivo(Data Stream Clustering)Descubrimiento de Rutas(Educational Process Mining)Almacén de Estado:Perfiles Dinámicos(Esquema Semiestructurado)Almacén de Estado:Modelos de Procesos(Esquema en Grafos)Servicio de Visualizacióne Interpretabilidad [Grafos de Proceso yEvolución de Clústeres]Acciones crudasFlujo de eventosLectura continuaVectores agregados (Ventanas)Trazas secuencialesActualización incrementalTopología de transicionesConsulta de baja latenciaModelos interpretablesDado que el funcionamiento integral de esta arquitectura depende directamente de la

naturaleza temporal de la información y de la manera en que esta se estructura, segmenta y

resguarda, en la siguiente sección se formaliza el modelo conceptual de los datos, contrastando

el tratamiento estático tradicional con el procesamiento de flujos continuos y estableciendo la

estrategia de persistencia del sistema.

III.2 Modelo conceptual, naturaleza del flujo y persistencia de datos

El desempeño metodológico de una arquitectura unificada orientada a eventos depende

de definir con precisión tanto la naturaleza temporal de los datos de entrada como la estrategia

de persistencia que soporta su procesamiento. En esta sección se establece la transición desde el

análisis estático tradicional hacia el tratamiento de flujos continuos mediante ventanas de tiem-

po, y posteriormente se describen los dos dominios de persistencia de la plataforma: el registro

inmutable de eventos canónicos y el almacén de estado operativo.

III.2.1 De los datos estáticos tradicionales al flujo continuo mediante ventanas dis-

juntas

En el enfoque tradicional de la Minería de Datos Educativos, la información extraída de

un LMS se trata como un conjunto de datos estático (datos en reposo). Bajo este esquema, las

bitácoras de interacción se exportan en bloques cerrados al finalizar una unidad temática o un

periodo escolar completo, consolidándose en tablas fijas que se analizan de forma retrospectiva.

Si bien este paradigma simplifica la aplicación de algoritmos clásicos de aprendizaje automático

por lotes, asume implícitamente que los patrones de comportamiento estudiantil son estacionarios

durante todo el periodo analizado, impidiendo capturar la evolución progresiva del alumno a lo

largo del curso.

En contraste, el modelo de datos adoptado en esta investigación concibe la actividad

dentro del LMS como un flujo continuo de datos (data stream): una secuencia ordenada y po-

tencialmente no acotada de eventos que arriban de manera asíncrona conforme los estudiantes

interactúan con los recursos pedagógicos. Para operar algorítmicamente sobre este flujo sin in-

currir en la acumulación indefinida propia de las tablas estáticas, se retoma la abstracción de

ventanas de tiempo fundamentada en el Capítulo 2 (Sección II.1.4 y Figura II.1).

Particularmente para este trabajo se utilizan ventanas de tiempo disjuntas (tumbling

21

windows). Considerando que el sistema recibe un flujo continuo de datos, este se particiona

como un conjunto secuencial de ventanas disjuntas en el tiempo de longitud fija ∆t, sin solapa-

miento entre intervalos consecutivos. Bajo este mecanismo, cada evento registrado en el flujo

pertenece exactamente a una ventana temporal Wk = (tk−1, tk]. Esta decisión de diseño ofrece

dos ventajas clave para el modelado educativo: por un lado, delimita periodos discretos y cohe-

rentes de observación (por ejemplo, cortes semanales o por bloque instruccional) a partir de los

cuales se calculan los vectores de características agregadas y las trazas de interacción; por otro

lado, al evitar el solapamiento entre ventanas adyacentes, impide el doble conteo de eventos y

facilita la comparación consistente y reproducible de la evolución de los perfiles estudiantiles

entre periodos consecutivos.

III.2.2 Registro canónico inmutable (Bitácora de adición)

En consonancia con los principios de la arquitectura Kappa, el núcleo de verdad histórica

del sistema se sustenta en una estructura de registro secuencial de sólo adición (append-only

log). En este repositorio, ninguna entrada puede ser modificada ni eliminada una vez registrada,

preservando de manera fidedigna la causalidad y secuencia estricta en que ocurrieron los eventos

en el entorno virtual de aprendizaje.

Este archivo histórico cumple dos propósitos fundamentales:

1. Trazabilidad y auditoría experimental: Permite reproducir íntegramente las secuencias

de interacción para la validación y comparación de modelos analíticos en fases posteriores.

2. Reconstrucción determinista del estado: En caso de ajustes algorítmicos, cambios en la

amplitud ∆t de las ventanas disjuntas o fallos de infraestructura, el sistema puede reprodu-

cir el flujo histórico desde cualquier instante temporal, recalculando los perfiles dinámicos

de forma consistente.

Conceptualmente, las entidades almacenadas en este registro inmutable adoptan una re-

presentación basada en eventos estructurados, definidos formalmente por la tupla E = ⟨u, a, r, t, M ⟩,

donde:

u representa el identificador unívoco del sujeto de aprendizaje.

a denota la acción o verbo ejecutado dentro de la plataforma (por ejemplo, visualización,

envío o retroalimentación).

22

r especifica el recurso pedagógico o entidad instruccional sobre la cual recae la interacción.

t constituye la estampa cronológica (timestamp) estandarizada que fija el momento exacto

del acontecimiento y determina su asignación a la ventana disjunta correspondiente.


M simboliza un conjunto de metadatos contextualmente enriquecidos (parámetros de se-

sión, identificadores de agrupamiento o contexto del curso).

III.2.3 Almacén de estado operativo y esquemas de representación

A diferencia del registro inmutable, diseñado para la escritura secuencial continua, el

almacén de estado contiene las representaciones actualizadas de los modelos computacionales

resultantes tras el procesamiento de cada ventana temporal. Su función principal es proveer ac-

ceso directo y desacoplado hacia la capa de presentación, además de servir como memoria de

trabajo para los algoritmos analíticos concurrentes.

El almacenamiento operativo se organiza mediante esquemas híbridos, seleccionando la

abstracción de datos más adecuada para cada tipo de entidad:

III.2.3.1 Esquema para perfiles dinámicos (Modelo semiestructurado)

El perfil del estudiante no constituye una estructura estática de dimensiones rígidas, sino

un esquema dinámico que evoluciona de manera continua. Por consiguiente, se define bajo un

paradigma de modelado semiestructurado jerárquico. Esta elección permite que la entidad del

usuario incorpore de forma fluida nuevos atributos conductuales, métricas agregadas por ventana

y pertenencias a agrupamientos (clusters) sin exigir la redefinición de esquemas globales.

La estructura lógica de cada perfil comprende:

Identificadores de contexto: Sujeto, curso y ventana temporal de observación.

Vector de características agregadas: Frecuencia de acceso por tipo de recurso, regulari-

dad de participación y tasa de completitud de tareas calculadas sobre la ventana disjunta

activa.

Estado analítico evolutivo: Pertenencia al grupo de comportamiento asignado por el al-

goritmo incremental, junto con el historial de transiciones entre clústeres y los centroides

o microclústeres asociados a dicho estado.

23

III.2.3.2 Esquema para modelos de procesos (Modelo topológico basado en grafos)

La representación de las rutas empíricas descubiertas mediante Minería de Procesos Edu-

cativos (EPM) requiere preservar explícitamente las relaciones de causalidad y precedencia tem-

poral. Una estructuración estrictamente tabular fragmentaría la interpretación de estas trayec-

torias. En consecuencia, se adopta un esquema topológico modelado como un grafo dirigido

etiquetado G = (V, Eg, W ):

Vértices o Nodos (V ): Representan los estados de interacción o eventos de alto nivel al-

canzados por los estudiantes dentro del diseño instruccional.

Aristas dirigidas (Eg): Expresan las transiciones secuenciales observadas empíricamente

entre una actividad y su predecesora directa.

Pesos y propiedades (W ): Propiedades cuantitativas asociadas a los vértices y aristas que

expresan frecuencias de transición, tiempos medios de estancia y métricas de soporte se-

cuencial.

III.2.3.3 Esquema relacional para metadatos institucionales y configuración

Aquellos elementos que exhiben un comportamiento dimensional fijo, fuerte integridad

referencial y baja tasa de variación temporal se gestionan conceptualmente mediante un esque-

ma relacional normalizado. Esto incluye los catálogos del diseño instruccional, identificadores

de cursos, prerrequisitos curriculares y la asignación formal de roles educativos, garantizando

consistencia transaccional e integridad en el contexto académico.

Esta segregación conceptual entre un flujo de eventos inalterable —segmentado tem-

poralmente mediante ventanas disjuntas— y almacenes de estado optimizados para estructuras

semiestructuradas y topológicas constituye el cimiento sobre el cual operan las capas funcionales

descritas a continuación.

III.3 Estructuración funcional por capas

Para materializar las funciones formalizadas en la Sección III.1 y operar de manera cohe-

rente con el modelo de datos y persistencia establecido en la Sección III.2, la solución compu-

tacional organiza su comportamiento en tres capas operativas cohesivas y desacopladas. Esta

subdivisión gobierna sistemáticamente el ciclo de vida de los datos educativos: desde su cap-

24

tura en el entorno virtual como eventos atómicos, pasando por su transformación en modelos

incrementales, hasta su proyección como información pedagógicamente accionable.

La separación en capas garantiza que las responsabilidades de telemetría, procesamiento

algorítmico y visualización evolucionen de forma independiente, preservando la continuidad del

flujo analítico sin inducir dependencias operativas que comprometan la consistencia del sistema.

A continuación, se detalla la dinámica conceptual de cada estrato y la manera en que los datos

se transforman progresivamente a través de ellos.

III.3.1 Capa de extracción e ingesta de datos

La capa de extracción e ingesta constituye el punto de entrada primario del sistema y

tiene como función cardinal capturar, de forma continua y no bloqueante, las acciones que los

estudiantes efectúan en el entorno virtual de aprendizaje. Tradicionalmente, la recolección de

interacciones escolares se ha apoyado en consultas periódicas por lotes a las bases de datos

transaccionales, lo que introduce retrasos temporales y sobrecarga en los servidores educativos.

En contraste, dentro de la arquitectura unificada propuesta, esta capa opera bajo un paradigma

orientado a eventos, donde cada interacción actúa como un emisor atómico de información en el

instante de su ocurrencia.

III.3.1.1 Dinámica funcional y flujo de datos en la ingesta

El flujo de datos a través de esta etapa se desarrolla en tres fases secuenciales:

1. Detección y emisión del evento crudo: Cuando el usuario interactúa con el LMS, el en-

torno virtual dispara una notificación asíncrona. En este nivel, los datos se encuentran en

un estado crudo y heterogéneo, condicionados por los identificadores propios de la sesión

del entorno de origen.

2. Recepción y amortiguamiento desacoplado: Un componente de recepción asíncrona cap-

tura la notificación sin forzar a la plataforma educativa a esperar el procesamiento analítico.

Esta función de amortiguamiento (buffering) previene la pérdida de registros ante picos de

concurrencia masiva, tales como evaluaciones simultáneas o cierres de entregas, y favorece

la disponibilidad del sistema.

3. Normalización mínima e inserción canónica: Los datos crudos recibidos se convierten

25

en la tupla básica de evento E = ⟨u, a, r, t, M ⟩ definida en la Sección III.2.2 y se escriben

inmediatamente en el registro continuo inmutable (append-only log). En este punto, los

eventos quedan formalmente ordenados en el tiempo y disponibles para su lectura analítica

posterior.

III.3.2 Capa de análisis y procesamiento de datos

Esta capa representa el núcleo computacional de la propuesta y asume la responsabili-

dad de transformar el flujo de eventos inmutables en modelos dinámicos e interpretables. Para

conciliar la tasa de llegada de eventos con el rigor pedagógico requerido, esta etapa se subdivide

funcionalmente en dos módulos coordinados: el preprocesamiento de abstracción semántica y el

modelado analítico concurrente dual.

III.3.2.1 Preprocesamiento, consolidación y abstracción semántica

Los eventos alojados en el flujo continuo presentan un nivel de granularidad compu-

tacional atómico y contienen ruido operativo o transacciones técnicas irrelevantes para el aná-

lisis pedagógico Bogarín et al., 2018; Romero y Ventura, 2020. Por consiguiente, la tubería de

transformación ejecuta sobre el flujo las siguientes operaciones:

Filtrado de ruido y eventos espurios: Se descartan peticiones repetitivas, llamadas inter-

nas de sincronización o acciones administrativas que no aportan evidencia sobre el com-

promiso cognitivo del alumno.

Agrupamiento en Eventos de Alto Nivel (High-Level Events): Las acciones atómicas

se abstraen hacia categorías semánticas estandarizadas basadas en el diseño instruccional;

por ejemplo, se consolidan múltiples peticiones técnicas de navegación como una acción

unificada de exploración de recursos Zavaleta-Sanchez et al., 2025.

Bifurcación representativa por ventana temporal: Conforme se completa cada ventana

de tiempo disjunta definida en la Sección III.2.1, el módulo genera concurrentemente dos

estructuras de datos complementarias a partir de los eventos limpios y enriquecidos:

1. Trazas de interacción ordenadas: Secuencias cronológicas de actividades identifica-

das por estudiante y delimitadas dentro de la ventana temporal correspondiente, pre-

servando la precedencia de acciones para alimentar el análisis estructural mediante

26

Minería de Procesos Educativos.

2. Vectores de características agregadas: Estructuras multidimensionales calculadas so-

bre el intervalo finito ∆t de la ventana disjunta, destinadas a alimentar el agrupamiento

evolutivo.

III.3.2.2 Modelado concurrente dual

Las estructuras de datos resultantes del preprocesamiento se distribuyen en paralelo hacia

dos motores analíticos incrementales que operan en simultáneo:

1. Tubería de agrupamiento evolutivo sobre flujos (Data Stream Clustering):

Comportamiento de los datos: Recibe los vectores de características cuantitativas ge-

nerados al cierre de cada ventana disjunta.

Función algorítmica: Actualiza de forma incremental los centroides y microclústeres

que definen los perfiles de comportamiento. Si un estudiante altera sustancialmente su

frecuencia o hábitos de interacción entre ventanas consecutivas, el algoritmo transfiere

su pertenencia hacia el nuevo perfil correspondiente sin requerir el reentrenamiento

global de la historia previa.

Destino: El estado actualizado de los perfiles dinámicos se persiste directamente en

el almacén de estado semiestructurado.

2. Tubería de minería de procesos educativos (Educational Process Mining):

Comportamiento de los datos: Consume las trazas secuenciales de eventos asociadas

a cada grupo de comportamiento descubierto.

Función algorítmica: Aplica algoritmos de descubrimiento de procesos para inferir las

relaciones de dependencia y precedencia temporal entre actividades pedagógicas. En

lugar de generar métricas abstractas de predicción, esta función mapea empíricamente

la trayectoria de navegación del estudiante.

Destino: Las transiciones descubiertas y sus pesos de soporte se formalizan como

grafos dirigidos que se almacenan en el almacén de estado topológico.

27

III.3.3 Capa de presentación e interpretabilidad

La capa de presentación cierra el ciclo analítico fungiendo como el canal de comunica-

ción entre los modelos computacionales resultantes y el usuario final (principalmente docentes).

Su objetivo no se limita al despliegue estético de tableros informativos, sino a garantizar la ex-

plicabilidad algorítmica de la solución, resolviendo el problema de la opacidad propio de los

sistemas de “caja negra”.

III.3.3.1 Flujo y transformación hacia la interpretabilidad

Esta capa opera de manera desacoplada del procesamiento continuo mediante la consulta

directa al almacén de estado operativo:

Consulta desacoplada al estado materializado: En lugar de consultar el registro inmu-

table histórico o interferir con el motor analítico de flujos, la interfaz solicita únicamente

las vistas materializadas del estado actual (perfiles dinámicos y topologías de grafos).

Mapeo hacia representaciones cognitivas: Los valores numéricos y matrices de adya-

cencia de los modelos se transforman en abstracciones visualmente intuitivas:

1. Exposición del estado dinámico: Visualización de la evolución temporal y distribu-

ción de los clústeres a lo largo de las ventanas disjuntas, evidenciando cuándo y por

qué un estudiante transitó de un nivel de interacción a otro.

2. Explicación estructural del comportamiento: Despliegue de grafos de flujo directo de

actividades que trazan empíricamente las secuencias seguidas por el alumno. Esto per-

mite identificar visualmente cuellos de botella instruccionales, desviaciones respecto

a la ruta sugerida o patrones de abandono de tareas.

De este modo, los datos fluyen hacia el educador no como predicciones aisladas, sino

como justificaciones empíricas contextualizadas que facilitan la toma de decisiones pedagógicas

oportunas.

III.3.4 Resumen del capítulo

En este capítulo se ha delineado la concepción arquitectónica general y el diseño con-

ceptual de la propuesta orientada al modelado dinámico e interpretable del comportamiento es-

28

tudiantil en plataformas de aprendizaje. En primera instancia, se presentó la solución compu-

tacional fundamentada en una arquitectura unificada tipo Kappa, explicando sus cuatro etapas

funcionales y su capacidad para superar la desarticulación propia de los enfoques tradicionales

por lotes.

Posteriormente, se formalizó el modelo conceptual de los datos, contrastando el trata-

miento estático tradicional con el procesamiento de flujos continuos particionados mediante

ventanas de tiempo disjuntas (tumbling windows). Asimismo, se estructuró la estrategia de per-

sistencia en dos dominios complementarios: un registro continuo inmutable de sólo adición para

garantizar la verdad histórica y la reproducibilidad metodológica, en coexistencia con almace-

nes de estado operativo semiestructurados y topológicos. Finalmente, se detallaron las respon-

sabilidades de las capas operativas de extracción orientada a eventos, análisis concurrente dual

(agrupamiento evolutivo y minería de procesos) y presentación enfocada en la interpretabilidad

docente.

Una vez fundamentado el modelo conceptual del sistema y establecidas las transforma-

ciones que experimentan los datos a lo largo de cada etapa, el siguiente capítulo abordará la

materialización tecnológica de esta arquitectura, detallando las herramientas de software, biblio-

tecas algorítmicas, gestores de bases de datos y protocolos de comunicación seleccionados para

su implementación formal.

29

Referencias

Abyaa, A., Khalidi Idrissi, M., & Bennani, S. (2019). Learner modelling: systematic review of the literature
from the last 5 years. Educational Technology Research and Development, 67(5), 1105-1143.
https://doi.org/10.1007/s11423-018-09644-1

AlQaheri, H., & Panda, M. (2022). An Education Process Mining Framework: Unveiling Meaningful Infor-
mation for Understanding Students’ Learning Behavior and Improving Teaching Quality. Informa-
tion, 13, 29. https://doi.org/10.3390/info13010029

Arrieta, A. B., Díaz-Rodríguez, N., Ser, J. D., Bennetot, A., Tabik, S., Barbado, A., Garcia, S., Gil-Lopez,
S., Molina, D., Benjamins, R., Chatila, R., & Herrera, F. (2020). Explainable Artificial Intelligence
(XAI): Concepts, taxonomies, opportunities and challenges toward responsible AI. Information
Fusion, 58, 82-115. https://doi.org/10.1016/j.inffus.2019.12.012

Batool, K., & Abbas, G. (2021). A Comprehensive Review on Evolving Data Stream Clustering. 2021
International Conference on Communication Technologies (ComTech), 138-143. https://doi.org/
10.1109/ComTech52583.2021.9616754

Bogarín, A., Cerezo, R., & Romero, C. (2018). A survey on educational process mining. WIREs Data

Mining and Knowledge Discovery, 8(1), e1230. https://doi.org/10.1002/widm.1230

Brusilovsky, P., & Millán, E. (2007). User Models for Adaptive Hypermedia and Adaptive Educational Sys-
tems. En The Adaptive Web: Methods and Strategies of Web Personalization (pp. 3-53). Springer.
https://doi.org/10.1007/978-3-540-72079-9_1

Chrysafiadi, K., & Virvou, M. (2013). Student modeling approaches: A literature review for the last decade.
Expert Systems with Applications, 40(11), 4715-4729. https://doi.org/10.1016/j.eswa.2013.02.
007

Desai, C. (2025). Explainable AI for Student Performance Prediction in E- Learning Environments. 14,

128-132.

Fischer, G. (2001). User Modeling in Human--Computer Interaction. User Modeling and User-Adapted

Interaction, 11(1--2), 65-86. https://doi.org/10.1023/A:1011145532042

Gama, J. (2010). Knowledge Discovery from Data Streams. Chapman; Hall/CRC. https://doi.org/10.1201/

EBK1439826119

Kundavaram, V. N. K. (2025). Implementation of Real-Time Event-driven data engineering using Azure
Fabric with Stream Analytics. International Journal of Data Science and IoT Management System,
4, 341-349. https://doi.org/10.64751/ijdim.2025.v4.n3.pp341-349

Lee, C., Luo, L., Kuhlmann, S. L., Plumley, R. D., Panter, A. T., Bernacki, M. L., Greene, J. A., & Gates,
K. M. (2025). Interpretable Predictive Analytics for Online Learning. Journal of Learning Analytics,
12, 259-278. https://doi.org/10.18608/jla.2025.8375

Mercado, J. F., Mendoza-Cardenas, C., Gaviria-Gomez, N., Fletscher, L., & Botero, J. F. (2024). Pre-
dicting Student Performance in a Non-linear Self-Paced Moodle Course. Proceedings of the
22nd LACCEI International Multi-Conference for Engineering, Education and Technology (LAC-
CEI 2024): “Sustainable Engineering for a Diverse, Equitable, and Inclusive Future at the Service
of Education". https://doi.org/10.18687/LACCEI2024.1.1.1412

Romero, C., & Ventura, S. (2020). Educational data mining and learning analytics: An updated survey.
WIREs Data Mining and Knowledge Discovery, 10(3), e1355. https://doi.org/10.1002/widm.1355
Semler, R. F., Semler, J. R., Wehrmeister, M. A., Southier, L. F. P., Casanova, D., & Teixeira, M. (2025).
Educational process mining: literature classification, gaps, and emerging opportunities. Frontiers
in Education, 10. https://doi.org/10.3389/feduc.2025.1543761

Setiadi, H., Josi, F. A. I., Winarno, Doewes, A., & Damayanti, R. W. (2025). Optimizing Student Per-
formance Prediction: A Comparative Analysis of Regression Algorithms and Feature Selection
Techniques on LMS Log Data. Vietnam Journal of Computer Science, 1-42. https://doi.org/10.
1142/S2196888825500265

Supriyanto, S., Ismail, T., & Setyawan, F. (2025). Discovering Student Learning Paths: An Educational
Process Mining Approach in Moodle. International Journal of Advances in Data and Information
Systems, 6, 692-704. https://doi.org/10.59395/ijadis.v6i3.1437

30

Turnbull, D., Chugh, R., & Luck, J. (2020). Learning Management Systems: An Overview. Encyclopedia
of Education and Information Technologies, 1052-1058. https://doi.org/10.1007/978- 3- 030-
10576-1_248

Zahoor, S., & Sofi, S. A. (2025). Data Mining for Cognitive e-Learning Systems: A Survey. Procedia Com-

puter Science, 259, 1803-1808. https://doi.org/10.1016/j.procs.2025.04.135

Zavaleta-Sanchez, M. Y., Benitez-Guerrero, E., Molero-Castillo, G. G., Mezura-Godoy, C., & Montane-
Jimenez, L. G. (2025). A Framework for Dynamic User Modeling Integrating Data Stream Mining
and Process Mining in Educational Contexts. IEEE Access, 13, 166078-166103. https://doi.org/
10.1109/ACCESS.2025.3611957

31

                “Lis de Veracruz: Arte, Ciencia, Luz”  www.uv.mx