# ADR-0001: Núcleo independente do AUTOSEG

Status: Aceita

Contexto: a arquitetura legada mistura GUI, OS e persistência. Precisamos reutilizar um motor de gestão para arte e serviços.

Decisão: criar Workaholic do zero com domínio genérico, configuração de entidades e persistência intercambiável. AUTOSEG integra por adaptador externo. Trabalho de GUI e fiscal permanece em módulos próprios.

Consequência: haverá trabalho adicional de migração, mas a reutilização deixa de depender de detalhes do legado.
