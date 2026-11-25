"""Classificação das licitações: segmento › subsegmento e natureza da contratação.

Como funciona
- O objeto é limpo do "juridiquês" do começo (registro de preços para..., contratação de empresa
  especializada para...). O que sobra é o NÚCLEO: as primeiras palavras que dizem o que se compra.
- Cada subsegmento tem palavras-chave (expressões regulares sem acento, minúsculas).
  Pontos = 3 por acerto no núcleo + 1 por acerto no resto do texto. Vence quem tiver mais pontos;
  empate fica com quem aparece primeiro na lista.
- A natureza (fornecimento de bens, prestação de serviços, obra/engenharia, consultoria,
  locação, credenciamento, alienação/concessão) vem do tipo de contratação descrito no objeto.

Para ajustar, edite as listas abaixo.
"""
import re
import unicodedata

# (segmento, subsegmento, palavras-chave)
TAXONOMIA = [
    # ---------------- Obras e engenharia
    ("Obras e engenharia", "Edificações e construções", r"obras? de (complementacao|conclusao|construcao|implantacao)|conclusao (da|de) obra|construcao d[aeo]s? (unidade|escola|creche|ubs|predio|sede|centro|ginasio|quadra|cobertura|unidades habitacionais|casas|moradias|muro|galpao|posto|capela|velorio|biblioteca|academia)|cobertura metalica|construcao civil|construcao d[aeo]s? |edificac|empreendimento habitacional|unidades habitacionais|habitacao de interesse|execucao (da|de) obra|obras? de construcao|conclusao (da|de) obra|construcao de"),
    ("Obras e engenharia", "Reformas e ampliações", r"\breforma|ampliac|readequac|adequac(ao|oes) (predial|fisica|estrutural)|recuperacao (estrutural|predial|de predio)|requalificac|restaurac"),
    ("Obras e engenharia", "Pavimentação e vias", r"pavimentac|pavimento|recapeament|asfalt|calcament|tapa[- ]buraco|estradas? (vicina|rura)|cascalhament|meio[- ]fio|sarjeta|paralelep|bloquete|operacao tapa|recuperacao de (vias|estradas|ruas)|patrolament"),
    ("Obras e engenharia", "Drenagem, pontes e contenções", r"drenagem|aguas pluviais|galeria|bueiro|\bpontes?\b|passarela|contenc|muro de arrimo|gabiao|encosta|erosao|barragem|acude|canaliz"),
    ("Obras e engenharia", "Praças, parques e urbanização", r"\bpracas?\b|parque|urbanizac|revitalizac|paisagism|orla|calcadao|ciclovia|espaco (publico|comunitario|de lazer)|academia ao ar livre"),
    ("Obras e engenharia", "Projetos e fiscalização de obras", r"projetos? (basico|executivo|complementar|arquitet|estrutural|de engenharia)|contratacao (semi-)?integrada|levantamento (topografic|planialtim|cadastral)|topograf|georreferenc|sondagem|fiscalizacao (de|da|das) obra|gerenciamento (de|da) obra|supervisao de obra|apoio tecnico a fiscalizacao|modelagem da informacao|\bbim\b"),
    ("Obras e engenharia", "Manutenção predial e instalações", r"manutencao predial|manutencao (preventiva|corretiva)( e (preventiva|corretiva))? (de|da|das|dos) (predio|edific|instalac|imove|unidades)|instalac(ao|oes) eletric|cabeamento estruturado|instalac(ao|oes) hidraul|telhado|impermeabiliz|pintura (predial|de predio|das unidades|interna|externa)|vidros|esquadria|serralheria|marcenaria|elevador|para-raio|\bspda\b|reparos? (predia|em predio)|pequenos reparos|\breparos?\b"),
    # ---------------- Saúde
    ("Saúde", "Medicamentos", r"medicament|farmac|insulina|vacina|soro fisiolog|antibiot|comprimid|ampola|contraste|nutricao enteral|formulas? (infanti|modificad|enteral|lactea)|suplemento alimentar|dietas? (enteral|especia)"),
    ("Saúde", "Materiais médico-hospitalares", r"materia(l|is) (medico|hospitalar|de enfermagem|odontolog|laboratorial|de consumo hospitalar)|insumos? (hospitalar|de saude|odontolog|para (saude|diabet))|seringa|agulha|luvas? de procedimento|curativ|sutura|cateter|\bsondas?\b|fraldas? geriatr|bolsa coletora|ostomia|gaze|esparadrapo|algodao hidrofilo|mascara cirurg|tiras? reagente|lanceta|glicemi"),
    ("Saúde", "Equipamentos médicos e odontológicos", r"equipamentos? (medic|hospitala|odontolog|de saude|de fisioterapia|laboratori)|cadeiras? de rodas|cama hospitalar|ultrassom|raio[- ]x|autoclave|desfibril|monitor multiparam|aparelhos? auditivo|orteses|proteses|opme|mobiliario hospitalar|consultorio odontolog"),
    ("Saúde", "Exames e laboratório", r"exames?|laborator|analises clinicas|diagnostico por imagem|tomograf|ressonancia|mamograf|endoscop|reagente|hemoterap|citopatolog|anatomopatolog"),
    ("Saúde", "Serviços médicos e terapias", r"servicos? medic|plantao|plantoes|medicos?( especialist)?|consultas|clinica|fisioterap|fonoaudiolog|psicolog|terapia|terapeut|home care|hemodialise|cirurgias?|procedimentos? (medic|cirurg)|pericias? medic|medicina do trabalho|odontolog|atencao (basica|primaria)|saude mental|enfermeir|internac"),
    # ---------------- Alimentação
    ("Alimentação", "Gêneros alimentícios e merenda", r"merenda|alimentacao escolar|generos? aliment|hortifrut|frutas|verduras|legumes|carnes?|frango|peixe|leite|laticin|panificac|\bpaes\b|polpa|graos|estocave|pereciv|agricultura familiar|chocolate|\bovos\b"),
    ("Alimentação", "Refeições prontas e lanches", r"refeic|marmit|lanches?|coffee break|buffet|almoco|jantar|kit lanche|alimentacao (preparada|pronta|para)"),
    ("Alimentação", "Água, café e copa", r"agua mineral|galao|\bcafe\b|acucar|cha |adocante|copa e cozinha|garrafoes"),
    # ---------------- Educação e cultura
    ("Educação e cultura", "Material didático, livros e kits escolares", r"didatic|livros?|apostila|kits? (escolar|pedagog|aluno)|materia(l|is) (escolar|pedagog)|brinquedos?|jogos pedagog|mochilas"),
    ("Educação e cultura", "Cursos, capacitação e treinamentos", r"\bcursos?\b|capacitac|treinamentos? (de|para|em|sobre)|formacao (continuada|profissional|de professores)|pos-graduacao|aulas (de|praticas)|oficinas? (de|pedagog)|palestras?|educador|professor|monitoria escolar|preparatorio|qualificacao profissional"),
    ("Educação e cultura", "Cultura e artes", r"artist|apresentac(ao|oes) (artistic|musica|cultura)|teatro|espetacul|danca|instrumentos? musica|bandas?\b|fanfarra|coral|biblioteca|museu|patrimonio historic|atracoes? (artistic|cultura|musica)|shows? musica|premio cultural|acervo"),
    ("Educação e cultura", "Concursos e processos seletivos", r"concurso publico|processo seletivo|vestibular|aplicacao de provas|banca (examinadora|organizadora)|cadernos? de provas"),
    ("Educação e cultura", "Vagas e serviços educacionais", r"vagas? (de|em) (educacao|ensino|creche|escola)|educacao infantil|instituic(ao|oes) (de ensino|educacionais)|escolas? particular|ensino (fundamental|medio|superior|tecnico|infantil)|bolsas? de estudo|sistema (de ensino|apostilado)"),
    # ---------------- Tecnologia
    ("Tecnologia da informação", "Software, sistemas e nuvem", r"software|sistemas? (informatizad|integrad|de gestao|web|de informac|de automac|de controle|de ponto)|licenc(a|as|iamento) (de uso|de software)|locacao de (sistema|software)|plataforma (digital|web|online|de)|aplicativo|whatsapp|chatbot|inteligencia artificial|nuvem|cloud|datacenter|hospedagem de (site|sistema)|portal (da transparencia|web)|desenvolvimento de (sistema|software|site)|seguranca da informac|antivirus|firewall|backup"),
    ("Tecnologia da informação", "Equipamentos e suprimentos de informática", r"computador|notebook|desktop|impressora|informatica|servidor(es)? (de rede|rack)|tablet|monitor(es)? (de video|led)?|nobreak|projetor|chromebook|toner|cartucho|suprimentos? de informat|switch|roteador|storage|perifericos|scanner"),
    ("Tecnologia da informação", "Internet e telecomunicações", r"internet|link (de dados|dedicado)|fibra optica|telecomunic|telefon|celular|radio comunic|radiocomunic|\bvoip\b|ramal|conectividade|wi-?fi"),
    ("Tecnologia da informação", "Suporte e outsourcing de TI", r"suporte tecnico|outsourcing|service desk|help desk|manutencao (de|em) (computador|equipamentos de informatica|impressoras)|locacao de (impressora|equipamentos de informatica|computador)|impressao corporativa|tecnologia da informacao"),
    # ---------------- Veículos e frota
    ("Veículos e frota", "Aquisição de veículos e máquinas", r"aquisicao de (veiculo|ambulancia|onibus|micro-?onibus|caminh|motocicleta|automove|maquina|trator|retroescavadeira|motoniveladora|pa carregadeira|escavadeira)|veiculos? (0 ?km|zero)|caminhao (basculante|pipa|compactador)|implementos agricola"),
    ("Veículos e frota", "Locação de veículos e máquinas", r"caminh(ao|oes) (cacamba|pipa|basculante|munck)|horas? maquinas?|maquinas? pesadas|retroescavadeira|motoniveladora|pa carregadeira|locacao de (veiculo|maquina|caminh|onibus|van|carro|automove|equipamentos pesados|retroescavadeira|trator)|maquinas? pesad|horas? maquina|com motorista|com operador"),
    ("Veículos e frota", "Manutenção, peças e pneus", r"pecas? (automotiv|para veiculo|genuina|de reposicao)|manutencao (preventiva e corretiva )?(de|da|dos|em) (veiculo|frota|maquina|onibus|ambulancia)|pneus?|camaras? de ar|baterias? automotiv|oficina|funilaria|mecanica|alinhamento|balanceamento|retifica|lubrificac|lavagem de veiculo"),
    ("Veículos e frota", "Combustíveis e gestão de frota", r"combustiv|gasolina|diesel|etanol|\barla\b|lubrificante|gestao de frota|cartao (combustivel|magnetico)|rastreament|telemetria"),
    # ---------------- Transporte
    ("Transporte e logística", "Transporte escolar", r"transporte escolar|transporte de (alunos|estudantes|universitario)"),
    ("Transporte e logística", "Transporte de pacientes e pessoas", r"transporte (de|sanitario) (pacientes|passageiros|pessoas|servidores|eletivo)|transporte sanitario|fretamento|translado de (pacientes|pessoas)"),
    ("Transporte e logística", "Fretes, mudanças e cargas", r"frete|mudanca|transporte de (cargas|materiais|mercadorias|bens|mobiliario)|logistic|entrega de|armazenag|courier|correspondencia"),
    ("Transporte e logística", "Passagens e hospedagem", r"passagens? (aere|rodovi)|agenciamento de viagens|hospedagem|hotel|diarias de hotel"),
    # ---------------- Limpeza e conservação
    ("Limpeza, conservação e higiene", "Serviços de limpeza e conservação", r"limpeza (d[aeo]s?|em) (escola|predio|unidade|imove|sede|ambiente|repartic|edific|hospital|posto)|servicos? (continuados )?de limpeza|limpeza (e conservacao|predial|hospitalar|de caixa|de fossa|de piscina)|conservacao predial|zeladoria|higienizac|desinfecc|lavanderia|copeiragem"),
    ("Limpeza, conservação e higiene", "Material de limpeza e higiene", r"materia(l|is) de (limpeza|higiene)|produtos? (de|para) (limpeza|higiene)|saneantes|detergente|desinfetante|papel (higienico|toalha)|sacos? (de|para) lixo|sabonete|alcool (em gel|70|etilico)|descartaveis|copos? descart"),
    ("Limpeza, conservação e higiene", "Dedetização e controle de pragas", r"dedetiz|desratiz|descupiniz|controle de pragas|controle de vetor|larvicida|fumigac"),
    # ---------------- Meio ambiente
    ("Meio ambiente e resíduos", "Coleta e destinação de resíduos", r"residuos?|\blixo\b|coleta (de|seletiva|convencional)|aterro|reciclag|destinacao final|transbordo|compostag|chorume|rss"),
    ("Meio ambiente e resíduos", "Limpeza urbana, poda e roçada", r"limpeza urbana|varric|rocad|capina|poda|supressao de arvores|arboriz|manejo de vegetacao|jardinagem|manutencao de areas verdes"),
    ("Meio ambiente e resíduos", "Gestão e licenciamento ambiental", r"ambiental|meio ambiente|licenciamento|recuperacao de area degradada|educacao ambiental|monitoramento (ambiental|de qualidade da agua)"),
    # ---------------- Saneamento
    ("Saneamento e água", "Tratamento de água e esgoto", r"tratamento de (agua|esgoto)|hipoclorito|\bcloro\b|fluossilic|coagulante|floculante|policloreto|sulfato de aluminio|carvao ativado|cal hidratada|produtos quimicos (para|de) tratamento|\beta\b|\bete\b"),
    ("Saneamento e água", "Redes, hidrômetros e bombas", r"hidrometro|macromedidor|ligacoes? (de agua|domiciliar)|rede de (distribuicao|abastecimento|agua|esgoto)|motobomba|bombas? (submers|dosadora|centrifug)|pocos? (artesian|tubular)|perfuracao de poco|reservatorio|adutora"),
    # ---------------- Segurança
    ("Segurança", "Vigilância e portaria", r"vigilancia (patrimonial|armada|desarmada)|seguranca (patrimonial|privada|armada|desarmada|nao armada)|vigilantes?|portaria|controlador de acesso"),
    ("Segurança", "Segurança eletrônica e monitoramento", r"cftv|cameras? (de seguranca|de monitoramento|de captura|de video)|video ?monitoramento|monitoramento (eletronic|por cameras|de imagens)|alarmes?|controle de acesso|cerca eletrica|leitura de placas|cerco eletronico|captura de imagens|central de monitoramento"),
    ("Segurança", "Prevenção e combate a incêndio", r"extintor|incendio|bombeiro|hidrantes?|brigada|ppci|avcb|sprinkler|deteccao de fumaca"),
    ("Segurança", "Equipamentos para forças de segurança", r"colete(s)? balistic|guarda (civil|municipal)|armamento|municao|algemas|tonfa|viatura policial|equipamentos? de protecao para guarda"),
    # ---------------- Mão de obra
    ("Mão de obra terceirizada", "Apoio administrativo e recepção", r"interpretes?|tradutor|\blibras\b|mao de obra|terceiriz|apoio administrativo|recepcionist|auxiliar administrativo|telefonista|agentes? de apoio|cessao de mao"),
    ("Mão de obra terceirizada", "Motoristas, operadores e serviços gerais", r"motoristas?|operadores? de maquina|servicos gerais|auxiliar de servicos|carregador|braçal|mao de obra operacional"),
    ("Mão de obra terceirizada", "Cuidadores, monitores e apoio escolar", r"cuidador|monitores? (escolar|de alunos)|apoio escolar|agente de apoio (educacional|escolar)|interprete de libras|acompanhante terapeutico"),
    # ---------------- Consultoria e serviços técnicos
    ("Gestão pública e projetos", "Projetos e programas públicos", r"(execucao|gestao|implementacao|implantacao|desenvolvimento|operacionalizacao|coordenacao) d[eo]s? (projetos?|programas?)|projetos? (sociais|socioeducativ|socioassistenc|culturais|educacionais|esportivos|pedagogicos|ambientais)|termo de (fomento|colaboracao)|organizac(ao|oes) da sociedade civil|\boscs?\b|edital de (fomento|premiacao)|lei (aldir blanc|paulo gustavo)|\bpnab\b"),
    ("Gestão pública e projetos", "Planejamento, planos e finanças públicas", r"plano (diretor|municipal|plurianual|de saneamento|de mobilidade|de residuos)|\bppa\b|\bldo\b|\bloa\b|consultoria (financeira|em gestao|administrativa|tributaria)|planejamento estrategico|gestao (publica|fiscal|de pessoas|de riscos|orcamentaria)|mapeamento de processos|reforma administrativa|plano de cargos|regularizacao fundiaria|cadastro (imobiliario|multifinalitario)|planta generica|geoprocessamento"),
    ("Gestão pública e projetos", "Modernização administrativa e arrecadação", r"recuperacao de (creditos|receita)|incremento (da|de) (receita|arrecadacao)|cadastro (imobiliario|multifinalitario|tecnico)|recadastramento|planta generica|georreferenc|regularizacao fundiaria|divida ativa|arrecadacao|modernizacao (administrativa|da gestao|tributaria)|compensacao previdenciaria|\bicms\b|valor adicionado fiscal|\bvaf\b|royalt"),
    ("Consultoria e serviços técnicos", "Assessoria jurídica e contábil", r"assessoria (juridica|contabil|tributaria|previdenciaria)|consultoria (juridica|contabil|tributaria|previdenciaria)|advocac|servicos? (juridicos|contabeis|advocaticios)|recuperacao de (creditos|tributos)|compensacao previdenciaria|revisao de (folha|tributos)"),
    ("Consultoria e serviços técnicos", "Auditoria, perícia e certificação", r"auditoria|pericia|perito|certificac(ao|ora)|avaliacao (atuarial|de imoveis|patrimonial)|calculo atuarial|inventario patrimonial|laudos? (tecnico|de avaliacao)|inspecao|vistoria tecnica|acreditacao"),
    ("Consultoria e serviços técnicos", "Estudos e assessoria técnica", r"consultoria|assessoria|estudos? (tecnic|de viabilidade|ambient|hidrolog|preliminar)|diagnostico (situacional|organizacional|socio|institucional|tecnico|ambiental)|elaboracao de (plano|estudo|relatorio|projeto de lei)|pesquisa (de opiniao|de satisfacao|de mercado)|captacao de recursos|convenios"),
    # ---------------- Comunicação e eventos
    ("Comunicação, publicidade e eventos", "Publicidade e divulgação", r"publicidade|propaganda|agencia de (publicidade|propaganda|comunicacao)|publicac(ao|oes) (de|em) (atos|jornal|diario)|atos oficiais|midia|veiculacao|radio (am|fm)|emissoras|campanhas? (publicitaria|educativa)|assessoria de (imprensa|comunicacao)|marketing|redes sociais"),
    ("Comunicação, publicidade e eventos", "Gráfica e comunicação visual", r"grafic|impressos?|impressao (de|grafica)|banners?|adesivos?|placas? (de identificacao|de inauguracao|de obra|indicativa)|faixas|folders?|cartazes|carimbos?|plotagem|comunicacao visual|letreiro|totem|envelopes? personalizad|cadernos? de provas|blocos? de|formularios"),
    ("Comunicação, publicidade e eventos", "Eventos, shows e festividades", r"ornament|decoracao (natalina|tematica|de natal)|natalin|cenograf|iluminacao (natalina|decorativa)|eventos?|show|palco|sonorizac|iluminacao cenica|tendas?|banheiros? quimico|festividade|\bnatal\b|carnaval|reveillon|aniversario d[aoe] (cidade|municipio)|\bfestas?\b|\bfeiras?\b|cerimonial|decoracao natalina|fogos de artificio|camarim|gerador para evento"),
    # ---------------- Mobiliário e equipamentos
    ("Mobiliário e equipamentos", "Móveis", r"mobiliario|moveis|cadeiras?|poltronas?|\bmesas?\b|armarios?|arquivos? de aco|estantes?|longarinas?|sofas?|beliche|colchao|carteiras escolares|conjunto aluno"),
    ("Mobiliário e equipamentos", "Eletrodomésticos e eletroportáteis", r"eletrodomestic|eletroportat|geladeira|refrigerador|freezer|bebedouro|purificador|fogao|forno|micro-?ondas|lavadora|secadora|liquidificador|ventilador|televis|smart tv|cafeteira|fritadeira|batedeira"),
    ("Mobiliário e equipamentos", "Ar-condicionado e climatização", r"ar[- ]condicionado|climatiz|split|refrigeracao|exaustor|cortina de ar|manutencao (de|em) ar"),
    ("Mobiliário e equipamentos", "Equipamentos diversos", r"equipamentos? (e materiais )?(de cozinha|industriais|para cozinha|de lavanderia|de academia|de som|audiovisual|fotografic)|fragmentadora|cofre|balanca|maquinas? de costura|camara fria|gerador(es)? de energia|roçadeira|motosserra|lavadora de alta pressao|ferramentas"),
    # ---------------- Materiais e suprimentos
    ("Materiais e suprimentos", "Material de expediente e escritório", r"expediente|papelaria|materia(l|is) de escritorio|papel (a4|sulfite|oficio)|canetas?|lapis|envelopes?|grampo|grampeador|clips?|pastas?|fichario|etiquetas?|toner"),
    ("Materiais e suprimentos", "Materiais de construção", r"materia(l|is) (de|para) construc|\bcimento\b|\bareia\b|brita|tijolo|blocos? (de concreto|ceramic)|argamassa|\bcal\b|telhas?|madeira|tintas?|ferragens?|vergalh|tubos? (de|pvc|de concreto)|conexoes|manilha|concreto usinado|pedra|piso ceramic|azulejo|massa corrida|aco (ca|para construc)"),
    ("Materiais e suprimentos", "Material elétrico e hidráulico", r"materia(l|is) eletric|materia(l|is) hidraul|cabos? eletric|fios? eletric|disjuntor|lampadas?|reatores?|tomadas?|interruptor|eletroduto|registros? (de gaveta|de pressao|hidraul|de esfera)|torneiras?|valvulas?|caixa d.?agua|bomba d.?agua"),
    ("Materiais e suprimentos", "Uniformes, EPI e têxteis", r"uniformes?|sapatos?|botas?\b|tenis\b|fardament|vestuario|calcados?|botinas?|\bepis?\b|equipamentos? de protecao individual|enxoval|roupas?|tecidos?|cobertores?|mantas?|toalhas|lencois|jalecos?|camisetas?|bones"),
    ("Materiais e suprimentos", "Material de consumo diverso", r"materia(l|is) de consumo|materiais diversos|utensilios|embalagens?|bobinas?|lonas?|cordas|pilhas|baterias? (alcalin|recarreg)"),
    # ---------------- Energia
    ("Energia e iluminação", "Iluminação pública", r"iluminacao publica|luminarias?|\bled\b|reles? fotoelet|postes?|eficientizacao"),
    ("Energia e iluminação", "Energia solar e eficiência", r"fotovoltaic|energia solar|usina solar|placas? solar|eficiencia energetica"),
    ("Energia e iluminação", "Fornecimento e infraestrutura elétrica", r"energia eletrica|mercado livre de energia|subestac|rede eletrica|transformador|gerador|grupo gerador|media tensao|alta tensao|baterias? estacionari"),
    # ---------------- Assistência social
    ("Assistência social", "Acolhimento e serviços socioassistenciais", r"acolhimento|abrigo|casa de passagem|situacao de rua|pessoa idosa|idosos|terceira idade|vulnerabilidade|protecao social|socioassistencial|assistencia social|cras|creas|scfv|convivencia e fortalecimento"),
    ("Assistência social", "Cestas, kits e benefícios", r"cestas? (basica|natalina|de alimentos)|kits? (natalin|de higiene|enxoval|bebe|maternidade)|fraldas|beneficios eventuais|auxilio (funeral|natalidade)|brinquedos natalinos|cobertores para"),
    # ---------------- Agropecuária
    ("Agropecuária e veterinária", "Insumos e serviços agrícolas", r"extensao rural|assistencia tecnica (rural|agricola|e extensao)|\bater\b|patrulha (mecanizada|agricola)|agricol|sementes?|adubo|fertiliz|calcario|mudas|insumos? agricol|mecanizacao agricola|aracao|gradagem|horas? de trator|corretivo de solo|agrotox|defensivos"),
    ("Agropecuária e veterinária", "Veterinária e animais", r"veterinar|castracao|zoonose|\bracao\b|bovinos?|vacinacao (animal|antirrabica)|caes|gatos|animais|bem-estar animal|inseminacao"),
    # ---------------- Financeiro
    ("Serviços financeiros e seguros", "Folha de pagamento e serviços bancários", r"instituic(ao|oes) (financeir|bancari)|bancari|folha de pagamento|consignad|arrecadacao|febraban|cooperativas? de credito|processamento .{0,30}creditos|meios de pagamento|maquinas? de cartao|\bpix\b"),
    ("Serviços financeiros e seguros", "Seguros", r"\bseguros?\b|seguradora|apolice"),
    # ---------------- Esporte
    ("Esporte e lazer", "Material e equipamentos esportivos", r"materia(l|is) esportiv|equipamentos? esportiv|\bbolas?\b|uniformes esportivos|redes de (volei|futebol)|trofeus?|medalhas|kimonos?|tatame"),
    ("Esporte e lazer", "Eventos e atividades esportivas", r"(eventos?|atividades?|competic(ao|oes)|modalidades?|escolinhas?|praticas?) (esportiv|de esporte)|arbitragem|campeonato|jogos (escolares|regionais|abertos|municipais)|torneio|atletas?|educador fisico|hidroginastica|beach tennis|corrida de rua|maratona|ginastica"),
    ("Esporte e lazer", "Playgrounds e academias ao ar livre", r"playground|parque infantil|academia ao ar livre|brinquedos (de|para) (praca|parque|playground)"),
    # ---------------- Trânsito
    ("Trânsito e mobilidade", "Sinalização viária", r"sinalizacao (viaria|horizontal|vertical|de transito|semaforica)|semaforo|lombada|redutor(es)? de velocidade|tachas?|faixas? de pedestre|placas? de (transito|sinalizacao|regulamentacao)|pintura (de|em) (faixa|via|solo)"),
    ("Trânsito e mobilidade", "Fiscalização e estacionamento", r"fiscalizacao eletronica|radar(es)? (fixo|de velocidade|estatic)|estacionamento rotativo|zona azul|talonario de multa|guincho|remocao de veiculos|patio de veiculos"),
    # ---------------- Imóveis, leilões e concessões
    ("Imóveis, leilões e concessões", "Locação de imóveis", r"locacao de (imovel|imoveis|predio|sala|galpao|espaco)|aluguel de (imovel|predio|sala|casa)"),
    ("Imóveis, leilões e concessões", "Leilões e alienação de bens", r"leiloeiro|\bleiloes?\b|alienacao|bens (patrimoniais )?inserviveis|venda (de|dos) bens|sucatas?"),
    ("Imóveis, leilões e concessões", "Concessões e permissões de uso", r"concessao (administrativa|onerosa|de uso|comum|do servico)|permissao de uso|parceria publico-privada|\bppp\b|cessao de uso|exploracao (comercial|de espaco)|quiosques?|lanchonete (no|na|do|da)"),
    # ---------------- Funerário
    # complementos (revisão de "Outros")
    ("Saúde", "Materiais médico-hospitalares", r"seringa|tubos? (cirurgic|endotraq|de silicone|de aspiracao)|produtos? (para|de) saude|agulhas?|introdutor|cateter|sondas?\b|curativ|ortes|protes|dispositivos? (ortoped|medic)|imobilizador|ventilator|saco mortuario|cobertura para cadaver|luvas (de procedimento|cirurgic)|gaze|esparadrapo|alcool (gel|espuma|70)|oxigenio|gases? medicina|\bopme\b|stent|marcapasso"),
    ("Saúde", "Equipamentos médicos e odontológicos", r"broncoscop|endoscopio|monitor multiparametr|desfibril|eletrocardiograf|autoclave|ultrassom|raio[- ]?x|bisturi|videolaringoscop"),
    ("Saúde", "Medicamentos", r"\bdietas?\b|suplementos? (alimentar|nutricion)|complemento alimentar|dieta enteral|fenilcetonuria|leites? especia"),
    ("Saúde", "Serviços médicos e terapias", r"servicos? de saude|procedimentos? (cirurgic|medic)|cirurgias?|hemodialise|protecao radiologica|radioterap|home care|atencao (basica|especializada)"),
    ("Alimentação", "Gêneros alimentícios e merenda", r"\bpao\b|\bpaes\b|biscoit|bolach|leite|arroz|feijao|alimentos|nutricao"),
    ("Veículos e frota", "Aquisição de veículos e máquinas", r"veiculos? (automotor|novos|zero|0 ?km|tipo|utilitario|de passeio)|automoveis|caminhonete|pick-?up|ambulancias?|motocicletas?"),
    ("Veículos e frota", "Manutenção, peças e pneus", r"lavage(m|ns) (de|dos) veiculo|lavagem automotiv|material rodante|guincho|reboque|\bpneus?\b|baterias? automotiv"),
    ("Veículos e frota", "Combustíveis e gestão de frota", r"gas liquefeito|\bglp\b|gas de cozinha|botijo"),
    ("Mão de obra terceirizada", "Motoristas, operadores e serviços gerais", r"pedreir|eletricista|encanador|carpinteir|pintor|horas? (de )?(maquina|trabalho)|diarias de (servico|trabalhador)"),
    ("Obras e engenharia", "Manutenção predial e instalações", r"granito|marmore|pias?\b|bancadas?|fechadura|portas?\b|janelas?|esquadria|vidros?|forro|pintura|impermeabiliz|telhado|serralheria|divisorias"),
    ("Tecnologia da informação", "Equipamentos e suprimentos de informática", r"\bdrones?\b|videowall|tablets?|monitores?|projetor|\bcabos? (de rede|hdmi|usb)"),
    ("Tecnologia da informação", "Software, sistemas e nuvem", r"background check|due diligence|plataforma (digital|web|online)|aplicativo|licencas? de uso|\bsaas\b|inteligencia artificial"),
    ("Consultoria e serviços técnicos", "Estudos e assessoria técnica", r"guarda (externa )?de documentos|digitalizacao de documentos|gestao documental|arquivo (fisico|permanente)"),
    ("Saneamento e água", "Redes, hidrômetros e bombas", r"fossas? septic|biodigestor|cisterna|poco artesiano|perfuracao de poco"),
    ("Educação e cultura", "Cursos, capacitação e treinamentos", r"instrutori|instrutor"),
    ("Comunicação, publicidade e eventos", "Gráfica e comunicação visual", r"brindes?|confeccao de (camisetas|bandeiras|faixas)"),
    ("Serviços funerários", "Serviços funerários e cemitérios", r"funerari|funebre|tanatopraxia|urnas? (mortuaria|funeraria)|sepultament|cemiterio|ossuario|necroteri|translado de corpos|exumac"),
]

NATUREZAS = [
    ("Credenciamento", r"^(chamamento publico.{0,60})?credenciamento|^pre-?qualificacao|credenciamento de (empresas|pessoas|profissionais|clinicas|laboratorios|instituic|prestadores|leiloeiros)"),
    ("Alienação, leilão ou concessão", r"leiloeiro|\bleilao\b|alienacao|venda de bens|concessao (administrativa|onerosa|de uso|comum|do servico)|permissao de uso|cessao de uso|parceria publico-privada"),
    ("Locação", r"^.{0,80}\b(locacao|aluguel)\b"),
    ("Obra ou serviço de engenharia", r"execucao (da|de|das|dos) obra|obras? de|construcao (de|da|do)|\breforma|ampliac|pavimentac|recapeament|calcament|drenagem|servicos? (comuns )?de engenharia|empreitada|contratacao (semi-)?integrada|engenharia para|instalacao (do|de) (sistema|usina) (de geracao|fotovoltaic|de energia)"),
    ("Consultoria ou serviço técnico especializado", r"consultoria|assessoria|auditoria|elaboracao de (plano|projeto|estudo|diagnostico|laudo)|projetos? (basico|executivo)|estudos? (tecnic|de viabilidade)|pericia|laudos?|servicos? tecnicos? especializado|levantamento topograf|georreferenc|planejamento"),
    ("Fornecimento de bens", r"aquisic|aquisicoes|compra|fornecimento (de|e entrega)|registro de precos? para (a )?(futura|eventual|futuras|eventuais)? ?(e )?(futura|eventual|futuras|eventuais)? ?(aquisic|fornecimento|compra)|^materia(l|is)|^generos|^equipamentos|^medicamentos"),
    ("Prestação de serviços", r"servico|prestacao|contratacao de (empresa|pessoa|instituic|entidade)|realizacao de|impressao|manutencao|limpeza|transporte|fornecimento de (refeic|mao de obra)"),
]

_TAX = [(seg, sub, re.compile(p)) for seg, sub, p in TAXONOMIA]
_NAT = [(n, re.compile(p)) for n, p in NATUREZAS]
OUTROS = "Outros"
SEGMENTOS = sorted(set(s for s, _, _ in TAXONOMIA))

_PREFIXOS = [
    r"^\s*\[[^\]]*\]\s*[-–:]?\s*",
    r"^\s*[a-z]{1,6}\s*n?[ºo.]?\s*[\d./-]*\d[\d./-]*\s*[-–:]\s*",
    r"^\s*(constitui\s+)?(o\s+)?objeto( d[ao] presente (licitacao|procedimento|edital|termo))?\s*(e|consiste em)?\s*:?\s*((a|o)\s+)?",
    r"^\s*a presente licitacao tem por objeto\s*((a|o)\s+)?",
    r"^\s*(ata de\s*)?(sistema de\s*)?registro de precos?\s*(para|de|visando)?\s*((a|o)\s+)?",
    r"^\s*(com lotes exclusivos[^,]*,\s*)?",
    r"^\s*(eventua(l|is)|futuras?|possivel)\s*(e\s*(futuras?|eventua(l|is)))?\s*",
    r"^\s*(aquisic(ao|oes)|compra|fornecimento)\s*(futuras?|parcelada|eventua(l|is))?\s*(e\s*(futuras?|eventua(l|is)|parcelada))?\s*(de|do|da|dos|das)?\s*",
    r"^\s*(a\s+)?contratacao\s*((semi-)?integrada\s*)?(futura\s*e\s*eventual\s*)?(de|da)?\s*(servicos\s*(de)?\s*)?(empresas?|pessoas?\s*juridicas?|instituic(ao|oes)|consorcio)?\s*(ou consorcio)?\s*(especializad[oa]s?|habilitad[oa]s?|de engenharia|da construcao civil)?\s*(em engenharia)?\s*,?\s*(para|na|em|no|de)?\s*((a|o)\s+)?",
    r"^\s*(prestacao|execucao)\s*(continuada|indireta)?\s*(de|dos|do)?\s*(servicos?)?\s*(tecnicos?\s*)?(especializados?\s*)?(de|em|para)?\s*",
]
_PREFIXOS = [re.compile(p) for p in _PREFIXOS]


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def nucleo(t: str) -> str:
    for _ in range(3):
        for p in _PREFIXOS:
            t = p.sub("", t)
    return t[:150]


_PROPOSITO = re.compile(r"[,;(]|\b(para (o |a |os |as )?(atender|atendimento|uso|suprir|compor|utilizacao|manutencao das|necessidade|demanda|composicao|realizacao de evento)|destinad|visando|em atendimento|a fim de|conforme|junto (a|ao|as)|no ambito|nas? (unidades?|escolas?|secretarias?|rede)|n[oa]s? (secretaria|municipio|prefeitura|hospital|centro)|d[ao]s? (secretaria|prefeitura|fundo municipal|camara)|pelo periodo|pelo prazo|durante)\b")


def cabeca(n: str) -> str:
    """O objeto em si: o trecho antes da finalidade ("para atender a Secretaria de Educação…")."""
    m = _PROPOSITO.search(n, 12)
    return n[:m.start()] if m else n


def classificar_completo(objeto: str):
    t = normalizar(objeto)
    n = " " + nucleo(t) + " "
    c = cabeca(n) + " "
    tt = " " + t + " "
    pontos = {}
    for seg, sub, rx in _TAX:
        hc = [m for m in rx.finditer(c)]
        hn = set(m.group(0) for m in rx.finditer(n))
        ht = set(m.group(0) for m in rx.finditer(tt))
        if not hc and not hn and not ht:
            continue
        p = 0.0
        if hc:  # o que está sendo contratado pesa muito mais que a área atendida
            p += 10 * min(len(set(m.group(0) for m in hc)), 2) + 4 * (1 - hc[0].start() / max(len(c), 1))
        p += 2 * min(len(hn), 2) + 0.5 * min(len(ht), 2)
        pontos[(seg, sub)] = pontos.get((seg, sub), 0) + p
    melhor = max(pontos, key=pontos.get) if pontos else None
    seg, sub = melhor if melhor else (OUTROS, "Sem classificação")
    nat = "Não identificada"
    inicio = re.sub(r"^\s*\[[^\]]*\]\s*[-–:]?\s*", "", t)
    if re.match(r"(pregao eletronico (srp )?para )?((sistema de )?registro de precos?\s*(para|de|visando)?\s*(a\s+)?)?((futuras?|eventua(l|is))\s*(e\s*)?)*(aquisic|compra|fornecimento (de|e entrega)|materia(l|is)|generos|medicamentos|equipamentos)", inicio):
        return seg, sub, "Fornecimento de bens"
    for nome, rx in _NAT:
        if rx.search(t):
            nat = nome
            break
    return seg, sub, nat


def classificar(objeto: str) -> str:
    return classificar_completo(objeto)[0]
