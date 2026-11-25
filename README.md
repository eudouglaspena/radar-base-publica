# Radar – base pública de inabilitações e impugnações

Robôs que leem, no PNCP (Portal Nacional de Contratações Públicas), os documentos públicos de pregões e concorrências
desde a Lei 14.133/2021: atas de sessão, julgamentos de habilitação, recursos, decisões, impugnações e esclarecimentos.

- `coletor/base_historica.py` lê um mês por vez; o workflow **Base histórica** percorre os meses.
- Os resultados ficam no ramo `base`, um diretório por mês (`indice`, `casos`, `participantes`, `documentos`, `estatisticas`).
- O workflow **Resumo** junta tudo em `aprendizados.json` (ramo `base`), usado pela plataforma.

Todos os dados vêm de fontes públicas.
