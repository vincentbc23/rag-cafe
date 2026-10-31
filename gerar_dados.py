"""
Gera o banco SQLite de fornecedores da cadeia do café com dados mockados.

Uso:
    python gerar_dados.py                 # ~1500 registros (padrão)
    python gerar_dados.py --total 400     # outro tamanho
    python gerar_dados.py --seed 7        # outro sorteio (a mesma seed gera sempre o mesmo banco)
Depois de gerar, rode de novo o indexar.py (o banco é recriado do zero).
Saída:
    fornecedores_cafe.db  (banco pronto)
    dados_mock.sql        (dump SQL com schema + inserts)
"""
import argparse
import os
import random
import sqlite3

DB_PATH = "fornecedores_cafe.db"
SCHEMA_PATH = "schema.sql"
DUMP_PATH = "dados_mock.sql"

# ---------------------------------------------------------------------------
# Regiões cafeeiras
# ---------------------------------------------------------------------------
REGIOES = {
    "Sul de Minas": ("MG", "35", ["Varginha", "Três Pontas", "Guaxupé", "Machado", "Alfenas",
                                  "Boa Esperança", "Campos Gerais", "Carmo de Minas",
                                  "São Sebastião do Paraíso", "Nepomuceno", "Poços de Caldas",
                                  "Nova Resende", "Muzambinho", "Cabo Verde", "Monte Santo de Minas",
                                  "Três Corações", "Elói Mendes", "Paraguaçu", "Carmo do Rio Claro",
                                  "Ilicínea", "Santana da Vargem", "Coqueiral", "Cambuquira"]),
    "Cerrado Mineiro": ("MG", "34", ["Patrocínio", "Araguari", "Monte Carmelo", "Patos de Minas",
                                     "Carmo do Paranaíba", "Serra do Salitre", "Campos Altos",
                                     "Coromandel", "Rio Paranaíba", "Ibiá", "Perdizes", "Estrela do Sul",
                                     "São Gotardo"]),
    "Matas de Minas": ("MG", "33", ["Manhuaçu", "Viçosa", "Caratinga", "Espera Feliz",
                                    "Simonésia", "Manhumirim", "Carangola", "Alto Jequitibá",
                                    "Lajinha", "Luisburgo"]),
    "Campo das Vertentes": ("MG", "35", ["Lavras", "Perdões", "Bom Sucesso", "Ijaci",
                                         "Santo Antônio do Amparo", "Itumirim", "Ingaí"]),
    "Mogiana": ("SP", "16", ["Franca", "Pedregulho", "Cristais Paulista", "Altinópolis",
                             "Espírito Santo do Pinhal", "Caconde", "Ribeirão Corrente", "Jeriquara",
                             "Patrocínio Paulista", "Itirapuã", "São Sebastião da Grama", "Mococa"]),
    "Montanhas do Espírito Santo": ("ES", "28", ["Venda Nova do Imigrante", "Brejetuba", "Iúna",
                                                 "Domingos Martins", "Castelo", "Afonso Cláudio",
                                                 "Conceição do Castelo", "Ibatiba", "Irupi",
                                                 "Muniz Freire"]),
    "Norte do Espírito Santo": ("ES", "27", ["Linhares", "São Gabriel da Palha", "Nova Venécia",
                                             "Jaguaré", "Vila Valério", "Sooretama", "Rio Bananal",
                                             "Águia Branca"]),
    "Chapada Diamantina": ("BA", "75", ["Piatã", "Mucugê", "Ibicoara", "Barra da Estiva", "Abaíra",
                                        "Ituaçu"]),
    "Oeste da Bahia": ("BA", "77", ["Luís Eduardo Magalhães", "Barreiras", "São Desidério"]),
    "Norte Pioneiro do Paraná": ("PR", "43", ["Pinhalão", "Carlópolis", "Tomazina", "Ibaiti",
                                              "Jacarezinho", "Ribeirão Claro", "Japira",
                                              "Joaquim Távora"]),
    "Matas de Rondônia": ("RO", "69", ["Cacoal", "Ministro Andreazza", "Alta Floresta D'Oeste",
                                       "Rolim de Moura", "Nova Brasilândia D'Oeste",
                                       "São Miguel do Guaporé"]),
}
PESOS_REGIAO = {
    "Sul de Minas": 24, "Cerrado Mineiro": 15, "Matas de Minas": 12, "Campo das Vertentes": 10,
    "Mogiana": 10, "Montanhas do Espírito Santo": 8, "Norte do Espírito Santo": 6,
    "Chapada Diamantina": 5, "Oeste da Bahia": 3, "Norte Pioneiro do Paraná": 4,
    "Matas de Rondônia": 4,
}
REGIOES_CONILON = {"Norte do Espírito Santo", "Matas de Rondônia"}
REGIOES_ESPECIAIS = {"Sul de Minas", "Chapada Diamantina", "Matas de Minas",
                     "Montanhas do Espírito Santo", "Cerrado Mineiro", "Campo das Vertentes"}
REGIOES_MECANIZADAS = {"Cerrado Mineiro", "Oeste da Bahia", "Mogiana"}

# ---------------------------------------------------------------------------
# Nomes
# ---------------------------------------------------------------------------
NOMES = ["João", "José", "Antônio", "Carlos", "Paulo", "Luiz", "Marcos", "Rafael", "Gustavo",
         "Pedro", "Lucas", "Mateus", "Rodrigo", "Fernando", "Sebastião", "Geraldo", "Adilson",
         "Wellington", "Diego", "Thiago", "Maria", "Ana", "Juliana", "Fernanda", "Patrícia",
         "Aparecida", "Luciana", "Camila", "Renata", "Mariana", "Beatriz", "Cláudia", "Tatiane",
         "Rosângela", "Letícia", "Vanessa"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento",
              "Lima", "Araújo", "Ribeiro", "Carvalho", "Gomes", "Martins", "Rocha", "Barbosa",
              "Moreira", "Rezende", "Vilela", "Junqueira", "Andrade", "Figueiredo", "Teixeira",
              "Mendes", "Campos", "Furtado", "Brandão", "Pimenta", "Siqueira", "Fonseca",
              "Castro", "Dias", "Freitas", "Mesquita", "Tavares", "Bernardes"]
FANTASIA = ["Grão Nobre", "Terra Boa", "Serra Azul", "Cafezal", "Bela Vista", "Nova Safra",
            "Boa Colheita", "Ouro Verde", "Santa Clara", "Três Irmãos", "Horizonte", "Vale Verde",
            "Raiz Forte", "Cerejinha", "Arábica", "Sol Nascente", "Pé de Serra", "Primavera",
            "Montanha Verde", "Café Forte", "Terra Roxa", "Planalto", "Bom Jardim", "Cafeicultor",
            "Rio Verde", "Serra da Mantiqueira", "Cerrado Vivo", "Grão de Ouro", "Colheita Farta",
            "Campo Bom", "Aroma do Campo", "Estrela do Vale", "Chapadão", "Água Limpa", "Bom Retiro",
            "São Bento", "Santa Luzia", "Vista Alegre", "Boa Vista", "Recanto", "Cachoeira",
            "Cafeeiro", "Rubi", "Catuaí", "Bourbon", "Mundo Novo", "Terra Firme", "Sítio Novo",
            "Fazendinha", "Agreste", "Pau Brasil", "Ipê Amarelo", "Jequitibá", "Aroeira"]


def nome_pessoa():
    sobs = random.sample(SOBRENOMES, k=2 if random.random() < 0.45 else 1)
    return " ".join([random.choice(NOMES), *sobs])


# ---------------------------------------------------------------------------
# Tipos de fornecedores
# nat: 'pf' | 'pj' | 'mix'  |  abr: 'local' | 'regional' | 'nacional'
# ---------------------------------------------------------------------------
TIPOS = []


def T(categoria, tipo_cadastro, tipo, nat, papel, unidade, pmin, pmax, abr, esp, frases,
      certs=(), n=(4, 6), nomes_pj=("{sob} {tipo}", "{fant} {tipo}")):
    TIPOS.append(dict(categoria=categoria, tipo_cadastro=tipo_cadastro, tipo=tipo, nat=nat,
                      papel=papel, unidade=unidade, pmin=pmin, pmax=pmax, abr=abr, esp=esp,
                      frases=frases, certs=certs, n=n, nomes_pj=nomes_pj))


S, P = "servico", "produto"

# ---------------- SERVIÇOS ----------------
C = "Planejamento e implantação da lavoura"
T(C, S, "Engenheiro agrônomo", "mix", "consultoria agronômica para cafeicultura",
  "visita técnica", 350, 900, "regional",
  ["recomendação de adubação", "nutrição do cafeeiro", "implantação de lavouras",
   "manejo de pragas e doenças", "planejamento de safra", "renovação de lavouras",
   "receituário agronômico", "cafés especiais"],
  ["Faz interpretação de análises de solo e foliar e monta o plano de adubação da safra.",
   "Acompanha a lavoura com visitas periódicas e emite receituário agronômico.",
   "Orienta a escolha de cultivares, espaçamento e densidade de plantio.",
   "Ajuda a planejar a renovação de talhões improdutivos com análise de custo."],
  certs=("CREA ativo", "Pós-graduação em cafeicultura", "Credenciado ATER"), n=(9, 11),
  nomes_pj=("{sob} Consultoria Agronômica", "{fant} Agronomia", "AgroTec {fant}"))
T(C, S, "Técnico agrícola", "pf", "técnico agrícola em lavouras de café",
  "visita técnica", 150, 350, "local",
  ["acompanhamento de lavoura", "coleta de amostras de solo", "monitoramento de pragas",
   "regulagem de pulverizadores", "controle de estoque de insumos"],
  ["Faz o acompanhamento de campo e a coleta de amostras de solo e folha.",
   "Monitora pragas como bicho-mineiro e broca e repassa relatórios ao produtor.",
   "Ajuda na regulagem de equipamentos de aplicação e calibração de adubadeiras."],
  certs=("Registro CFTA", "Curso de aplicação de defensivos"), n=(6, 8))
T(C, S, "Topógrafo", "mix", "topógrafo rural", "hectare", 80, 200, "regional",
  ["georreferenciamento", "curvas de nível", "demarcação de talhões", "levantamento planialtimétrico",
   "mapeamento com drone"],
  ["Faz a demarcação de talhões e o traçado de curvas de nível para plantio em áreas declivosas.",
   "Realiza georreferenciamento de imóveis rurais para CAR e regularização.",
   "Entrega mapas da propriedade com área útil e declividade."],
  certs=("CREA ativo", "Credenciado INCRA"),
  nomes_pj=("{sob} Topografia", "Geo{fant} Topografia"))
T(C, S, "Operador de máquinas para preparo de solo", "mix", "operador de máquinas para preparo de solo",
  "hora-máquina", 180, 320, "local",
  ["aração", "gradagem", "subsolagem", "sulcamento para plantio", "abertura de covas",
   "calagem e gessagem"],
  ["Presta serviço com trator e implementos próprios para preparar a área de plantio.",
   "Faz sulcamento e abertura de covas para implantação de lavouras novas.",
   "Aplica calcário e gesso a lanço antes do plantio."],
  certs=("CNH categoria C", "Curso de operador de máquinas agrícolas"),
  nomes_pj=("{sob} Serviços Agrícolas", "{fant} Máquinas e Serviços"))
T(C, S, "Projetista de irrigação", "mix", "projetista de sistemas de irrigação",
  "hectare (projeto)", 250, 600, "regional",
  ["gotejamento", "pivô central", "fertirrigação", "outorga de água", "dimensionamento de bombas"],
  ["Elabora projetos de irrigação por gotejamento e fertirrigação para café.",
   "Dimensiona bombas, filtros e linhas de acordo com o relevo e a disponibilidade de água.",
   "Auxilia no processo de outorga de uso de água junto ao órgão ambiental."],
  certs=("CREA ativo", "Especialização em irrigação e drenagem"),
  nomes_pj=("{fant} Irrigação Projetos", "{sob} Engenharia de Irrigação"))

C = "Manejo e tratos culturais"
T(C, S, "Aplicador de defensivos", "mix", "aplicador de defensivos agrícolas",
  "hectare", 80, 180, "local",
  ["pulverização com turbo-atomizador", "aplicação costal", "aplicação de herbicida",
   "aplicação foliar", "controle de ferrugem", "controle de broca"],
  ["Faz aplicação tratorizada com turbo-atomizador e aplicação costal em áreas declivosas.",
   "Trabalha com EPI completo e respeita intervalo de reentrada e carência.",
   "Possui equipamento próprio calibrado para aplicações de fungicida e inseticida."],
  certs=("NR-31", "Curso de aplicação segura de agrotóxicos"),
  nomes_pj=("{sob} Pulverização", "{fant} Aplicações Agrícolas"))
T(C, S, "Piloto de drone agrícola", "mix", "piloto de drone agrícola",
  "hectare", 60, 140, "regional",
  ["pulverização com drone", "mapeamento aéreo", "NDVI", "aplicação em áreas declivosas",
   "contagem de plantas"],
  ["Faz pulverização com drone em lavouras de montanha onde o trator não entra.",
   "Gera mapas de vigor (NDVI) para identificar falhas e reboleiras de pragas.",
   "Realiza aplicações rápidas com baixo volume de calda."],
  certs=("Registro no MAPA", "Cadastro ANAC/DECEA", "Curso CAAR"),
  nomes_pj=("{fant} Drones Agrícolas", "AeroAgro {fant}", "{sob} Drone Service"))
T(C, S, "Equipe de poda", "mix", "podador de café", "hectare", 700, 1800, "local",
  ["recepa", "esqueletamento", "decote", "desbrota", "poda com motosserra", "poda programada de ciclo"],
  ["Executa recepa, esqueletamento e decote conforme recomendação agronômica.",
   "Trabalha com equipe própria e motosserras e ferramentas de poda.",
   "Faz desbrota manual nas lavouras podadas."],
  certs=("NR-31", "Curso de operação de motosserra NR-12"), n=(6, 8),
  nomes_pj=("{sob} Poda de Café", "{fant} Serviços de Poda"))
T(C, S, "Trabalhador rural para tratos culturais", "pf", "trabalhador rural diarista",
  "diária", 110, 180, "local",
  ["capina", "arruação", "adubação manual", "roçada", "replantio", "esparramação"],
  ["Trabalha como diarista em capina, roçada e adubação manual.",
   "Tem experiência em arruação e esparramação antes e depois da colheita.",
   "Faz replantio de falhas e amarração de mudas."],
  certs=("NR-31",), n=(6, 8))
T(C, S, "Laboratório de análise de solo e foliar", "pj", "laboratório de análises agronômicas",
  "amostra", 45, 120, "regional",
  ["análise de solo", "análise foliar", "análise de micronutrientes", "análise de fertilizantes",
   "análise física de solo"],
  ["Recebe amostras de solo e folha e entrega laudos em poucos dias úteis.",
   "Oferece análise química completa com micronutrientes e matéria orgânica.",
   "Tem pontos de coleta e parceria com cooperativas da região."],
  certs=("Acreditação ISO 17025", "Participante do programa de qualidade de laboratórios"),
  nomes_pj=("Laboratório {fant}", "{sob} Análises Agronômicas", "AgroLab {fant}"))
T(C, S, "Consultor em manejo de pragas e doenças", "mix", "consultor em manejo integrado de pragas",
  "visita técnica", 300, 700, "regional",
  ["bicho-mineiro", "broca-do-café", "ferrugem", "cercosporiose", "nematoides", "MIP", "controle biológico"],
  ["Faz monitoramento de bicho-mineiro, broca e ferrugem e define o momento certo de aplicar.",
   "Implanta programas de manejo integrado de pragas (MIP) com uso de controle biológico.",
   "Ajuda a reduzir custos com defensivos por meio de amostragem e níveis de controle."],
  certs=("CREA ativo", "Mestrado em fitopatologia"),
  nomes_pj=("{fant} Fitossanidade", "{sob} Consultoria em MIP"))

C = "Colheita"
T(C, S, "Colhedor manual", "pf", "colhedor de café", "medida de 60 L", 20, 40, "local",
  ["derriça no pano", "colheita seletiva", "catação", "varrição", "colheita em montanha"],
  ["Trabalha na derriça no pano e na colheita seletiva de cereja madura.",
   "Tem experiência em colheita em lavouras de montanha.",
   "Faz catação e varrição do café do chão após a colheita."],
  certs=("NR-31",), n=(9, 11))
T(C, S, "Operador de derriçadeira", "pf", "operador de derriçadeira portátil", "diária", 180, 300, "local",
  ["derriçadeira portátil", "colheita semimecanizada", "manutenção de derriçadeira"],
  ["Opera derriçadeira portátil própria e rende mais que a colheita manual.",
   "Faz pequenas manutenções na máquina durante a safra.",
   "Trabalha junto com a turma no pano para acelerar a colheita."],
  certs=("NR-31", "NR-12"))
T(C, S, "Serviço de colheita mecanizada", "pj", "colheita mecanizada de café", "hora-máquina", 350, 650,
  "regional",
  ["colhedora automotriz", "colhedora tracionada", "recolhedora", "colheita em repasse",
   "regulagem de vibração"],
  ["Terceiriza a colheita com colhedora própria, operador e caminhão de apoio.",
   "Regula a vibração e velocidade para reduzir danos à planta e perdas.",
   "Faz a primeira passada e o repasse, além do recolhimento do café de chão."],
  certs=("NR-31", "NR-12"), n=(5, 7),
  nomes_pj=("{sob} Colheita Mecanizada", "{fant} Colheitas", "Colheita {fant}"))
T(C, S, "Empreiteiro de mão de obra rural", "mix", "empreiteiro de turmas de colheita",
  "diária por trabalhador", 150, 230, "regional",
  ["turma de colheita", "turma de poda", "mão de obra registrada", "alojamento e transporte",
   "gestão de equipe"],
  ["Fornece turmas completas de colheita com transporte e registro em carteira.",
   "Organiza as equipes e o controle de produção por medida colhida.",
   "Atende pedidos de turmas grandes no pico da safra."],
  certs=("NR-31", "Empresa com CNPJ e mão de obra registrada"),
  nomes_pj=("{sob} Serviços Rurais", "{fant} Mão de Obra Rural"))
T(C, S, "Transportador de café", "mix", "transportador de café e cargas rurais", "viagem", 250, 700,
  "regional",
  ["frete lavoura-terreiro", "frete para armazém", "caminhão basculante", "carreta",
   "transporte de café em big bag"],
  ["Faz o transporte do café da lavoura até o terreiro ou secador.",
   "Leva café beneficiado até armazéns e cooperativas.",
   "Trabalha com caminhão basculante e carreta."],
  certs=("ANTT", "CNH categoria E"),
  nomes_pj=("Transportes {sob}", "{fant} Logística Rural"))

C = "Pós-colheita e processamento"
T(C, S, "Operador de secador", "pf", "operador de secador de café", "diária", 160, 260, "local",
  ["secador rotativo", "secador de leito fixo", "controle de umidade", "controle de temperatura",
   "secagem de cafés especiais"],
  ["Controla temperatura e umidade da massa para não comprometer a qualidade do café.",
   "Tem experiência com secador rotativo e controle de fornalha a lenha.",
   "Trabalha em turnos durante a safra."],
  certs=("NR-31", "NR-13"))
T(C, S, "Terreirista", "pf", "terreirista", "diária", 120, 190, "local",
  ["esparramação no terreiro", "revolvimento", "leiras", "secagem em terreiro suspenso",
   "cobertura noturna"],
  ["Faz o manejo do café no terreiro com revolvimento correto e montagem de leiras.",
   "Tem experiência com secagem em terreiro suspenso para cafés especiais.",
   "Cuida da cobertura com lona em caso de chuva."],
  certs=("NR-31",))
T(C, S, "Operador de lavador e despolpador", "pf", "operador de lavador e despolpador",
  "diária", 150, 240, "local",
  ["cereja descascado", "despolpamento", "fermentação controlada", "separação de boia"],
  ["Opera o lavador para separar o café boia do cereja e verde.",
   "Faz o descascamento e despolpamento para produção de cereja descascado.",
   "Acompanha processos de fermentação controlada."],
  certs=("NR-31", "NR-12"), n=(3, 5))
T(C, S, "Serviço de beneficiamento de café", "pj", "beneficiamento de café",
  "saca de 60 kg", 6, 15, "regional",
  ["beneficiamento", "rebeneficiamento", "separação por peneira", "catação eletrônica",
   "padronização de lotes"],
  ["Presta serviço de beneficiamento com separação por peneira e densidade.",
   "Possui catadora eletrônica para retirada de defeitos.",
   "Monta e padroniza lotes para venda."],
  nomes_pj=("Beneficiadora {fant}", "{sob} Beneficiamento de Café"))
T(C, S, "Armazém de café", "pj", "armazenagem de café", "saca/mês", 1.5, 4, "regional",
  ["armazém geral", "armazenagem em big bag", "armazenagem em sacaria", "emissão de CDA/WA",
   "controle de umidade"],
  ["Armazena café em sacaria e big bag com controle de temperatura e umidade.",
   "Emite certificados de depósito para operações de crédito.",
   "Oferece amostragem e rastreabilidade dos lotes."],
  certs=("Armazém certificado MAPA",),
  nomes_pj=("Armazéns {fant}", "{sob} Armazéns Gerais"))

C = "Qualidade e comercialização"
T(C, S, "Classificador de café", "mix", "classificador de café", "amostra", 25, 60, "regional",
  ["classificação por tipo", "classificação por peneira", "contagem de defeitos",
   "classificação oficial"],
  ["Faz a classificação por tipo, peneira e defeitos conforme a tabela oficial.",
   "Emite laudo de classificação para negociação do café.",
   "Ajuda o produtor a entender o que desvaloriza o lote."],
  certs=("Classificador credenciado MAPA",),
  nomes_pj=("{fant} Classificação de Café", "{sob} Classificação"))
T(C, S, "Q-Grader / provador de café", "mix", "provador de café (Q-Grader)", "amostra", 120, 300,
  "nacional",
  ["análise sensorial", "pontuação SCA", "cafés especiais", "prova de xícara", "perfil sensorial",
   "preparação para concursos"],
  ["Faz a prova de xícara e pontua o café pelo protocolo SCA.",
   "Emite laudo sensorial com notas e descritores para venda de cafés especiais.",
   "Prepara lotes para concursos de qualidade."],
  certs=("Q-Arabica Grader (CQI)", "Q-Robusta Grader (CQI)", "Classificador credenciado MAPA"),
  nomes_pj=("{fant} Cafés Especiais", "Prova {fant}"))
T(C, S, "Corretor de café", "mix", "corretor de café", "% do valor negociado", 0.5, 1.5, "regional",
  ["intermediação de venda", "cafés especiais", "exportação", "contratos futuros", "venda de lotes"],
  ["Faz a intermediação entre produtor e compradores, exportadores e torrefações.",
   "Acompanha o mercado e orienta o melhor momento de venda.",
   "Trabalha com lotes de café commodity e especiais."],
  nomes_pj=("{sob} Corretora de Café", "{fant} Corretagem"))
T(C, S, "Consultor de cafés especiais", "mix", "consultor de cafés especiais", "visita técnica", 600,
  1500, "nacional",
  ["fermentação controlada", "processos naturais e anaeróbicos", "colheita seletiva",
   "rastreabilidade", "acesso a mercado de especiais"],
  ["Implanta processos de fermentação controlada e anaeróbica para elevar a pontuação.",
   "Treina a equipe em colheita seletiva e secagem para qualidade.",
   "Ajuda a acessar compradores e concursos de cafés especiais."],
  certs=("Q-Arabica Grader (CQI)", "Barista certificado SCA"),
  nomes_pj=("{fant} Specialty Coffee", "{sob} Consultoria em Cafés Especiais"))
T(C, S, "Torrefação por encomenda", "pj", "torrefação por encomenda", "kg torrado", 12, 25, "nacional",
  ["torra sob encomenda", "marca própria", "moagem", "embalagem com válvula", "perfis de torra"],
  ["Torra o café do produtor para ele vender com marca própria.",
   "Oferece moagem, embalagem com válvula e rótulo.",
   "Desenvolve perfis de torra de acordo com o lote."],
  nomes_pj=("Torrefação {fant}", "{sob} Torrefação"))

C = "Máquinas, estrutura e manutenção"
T(C, S, "Mecânico de máquinas agrícolas", "mix", "mecânico de máquinas agrícolas", "hora", 90, 180,
  "local",
  ["tratores", "colhedoras", "pulverizadores", "sistema hidráulico", "atendimento no campo"],
  ["Faz manutenção de tratores e implementos com atendimento na propriedade.",
   "Atende emergências durante a safra.",
   "Tem experiência com sistema hidráulico e motores diesel."],
  nomes_pj=("{sob} Mecânica Agrícola", "{fant} Mecânica Rural"))
T(C, S, "Técnico de manutenção de secadores e beneficiadoras", "mix",
  "técnico de manutenção de secadores e máquinas de beneficiamento", "hora", 110, 200, "regional",
  ["secadores", "fornalhas", "máquinas de beneficiamento", "elevadores de canecas", "revisão pré-safra"],
  ["Faz a revisão pré-safra de secadores, fornalhas e elevadores.",
   "Conserta máquinas de beneficiamento e catadoras.",
   "Atende chamados durante a safra."],
  certs=("NR-12", "NR-13"),
  nomes_pj=("{sob} Manutenção Industrial", "{fant} Manutenção de Secadores"))
T(C, S, "Eletricista rural", "pf", "eletricista rural", "hora", 70, 140, "local",
  ["rede trifásica", "motores elétricos", "quadros de comando", "instalação de secadores",
   "bombas de irrigação"],
  ["Faz instalações elétricas em tulhas, secadores e bombas de irrigação.",
   "Monta quadros de comando para motores.",
   "Faz manutenção preventiva antes da safra."],
  certs=("NR-10",))
T(C, S, "Construtor de terreiros e tulhas", "mix", "pedreiro especializado em estruturas rurais",
  "m²", 60, 140, "local",
  ["terreiro de concreto", "terreiro suspenso", "tulhas", "galpões", "barracões"],
  ["Constrói terreiros de concreto com caimento correto e drenagem.",
   "Executa tulhas e galpões para armazenagem.",
   "Monta terreiros suspensos para cafés especiais."],
  nomes_pj=("{sob} Construções Rurais", "{fant} Construtora Rural"))
T(C, S, "Soldador e serralheiro rural", "pf", "soldador e serralheiro", "hora", 70, 130, "local",
  ["solda de implementos", "estruturas metálicas", "portões e cercas", "reforma de carretas"],
  ["Faz soldas em implementos e reforma de carretas.",
   "Fabrica estruturas metálicas para galpões e terreiros suspensos.",
   "Atende na propriedade com máquina de solda portátil."])

C = "Gestão, certificação e serviços de apoio"
T(C, S, "Consultor de gestão rural", "mix", "consultor de gestão rural", "mês", 800, 3000,
  "regional",
  ["custo de produção", "fluxo de caixa", "planejamento financeiro", "indicadores de produtividade",
   "sucessão familiar"],
  ["Levanta o custo de produção por saca e monta o fluxo de caixa da fazenda.",
   "Acompanha indicadores e ajuda na tomada de decisão.",
   "Apoia o planejamento de investimentos e a sucessão familiar."],
  certs=("CRA ativo", "MBA em agronegócio"),
  nomes_pj=("{fant} Gestão Rural", "{sob} Consultoria em Agronegócio"))
T(C, S, "Contador rural", "mix", "contador rural", "mês", 350, 1200, "regional",
  ["livro caixa do produtor", "Imposto de Renda rural", "folha de pagamento rural", "ITR",
   "abertura de CNPJ rural"],
  ["Cuida do livro caixa do produtor e da declaração de Imposto de Renda.",
   "Faz a folha de pagamento dos safristas e o eSocial.",
   "Orienta a escolha entre pessoa física e jurídica na atividade rural."],
  certs=("CRC ativo",),
  nomes_pj=("{sob} Contabilidade Rural", "Contábil {fant}"))
T(C, S, "Consultor de certificações", "mix", "consultor de certificações",
  "projeto", 3000, 12000, "nacional",
  ["Rainforest Alliance", "4C", "orgânico", "Certifica Minas Café", "rastreabilidade",
   "boas práticas agrícolas"],
  ["Prepara a propriedade para auditorias de certificação.",
   "Monta a documentação de rastreabilidade e boas práticas.",
   "Treina a equipe para cumprir os requisitos socioambientais."],
  certs=("Auditor líder certificado", "CREA ativo"),
  nomes_pj=("{fant} Certificações", "{sob} Consultoria Socioambiental"))
T(C, S, "Engenheiro ambiental", "mix", "engenheiro ambiental", "projeto", 1500, 6000, "regional",
  ["CAR", "outorga de água", "licenciamento ambiental", "reserva legal", "PRAD"],
  ["Faz CAR, outorga de uso de água e licenciamento ambiental.",
   "Regulariza reserva legal e APP da propriedade.",
   "Elabora planos de recuperação de áreas degradadas."],
  certs=("CREA ativo",),
  nomes_pj=("{fant} Engenharia Ambiental", "{sob} Meio Ambiente"))
T(C, S, "Técnico em segurança do trabalho rural", "pf", "técnico em segurança do trabalho",
  "visita técnica", 250, 600, "regional",
  ["NR-31", "PGRTR", "treinamentos de segurança", "EPI", "adequação de alojamentos"],
  ["Adequa a propriedade à NR-31 e elabora o PGRTR.",
   "Ministra treinamentos para aplicadores e operadores de máquinas.",
   "Orienta sobre EPI e condições de alojamento da colheita."],
  certs=("Registro no MTE",))
T(C, S, "Consultor de crédito rural", "mix", "consultor de crédito rural", "% do crédito", 1, 3,
  "regional",
  ["Pronaf", "Pronamp", "Funcafé", "custeio", "investimento", "renegociação de dívidas"],
  ["Elabora projetos de custeio e investimento para bancos e cooperativas.",
   "Orienta sobre linhas como Pronaf, Pronamp e Funcafé.",
   "Ajuda na renegociação de dívidas rurais."],
  certs=("CREA ativo", "Certificação CPA-10"),
  nomes_pj=("{fant} Crédito Rural", "{sob} Projetos Agropecuários"))

# ---------------- PRODUTOS ----------------
C = "Insumos agrícolas"
T(C, P, "Revenda de fertilizantes e corretivos", "pj", "revenda de fertilizantes e corretivos",
  "tonelada", 1800, 4200, "regional",
  ["adubo NPK", "calcário", "gesso agrícola", "ureia", "cloreto de potássio", "formulados para café"],
  ["Vende adubos formulados para café, calcário e gesso agrícola.",
   "Oferece entrega na propriedade e condições de pagamento na safra.",
   "Tem agrônomo para recomendação de adubação sem custo adicional."],
  n=(8, 10), nomes_pj=("{fant} Fertilizantes", "{sob} Insumos Agrícolas", "Agro {fant}"))
T(C, P, "Revenda de defensivos agrícolas", "pj", "revenda de defensivos agrícolas",
  "litro (média do portfólio)", 80, 400, "regional",
  ["fungicidas", "inseticidas", "herbicidas", "acaricidas", "adjuvantes"],
  ["Vende fungicidas, inseticidas e herbicidas registrados para café.",
   "Emite receituário agronômico na hora da compra.",
   "Recebe embalagens vazias para devolução."],
  certs=("Revenda registrada no IMA/órgão estadual",), n=(6, 8),
  nomes_pj=("{fant} Defensivos", "{sob} Agroquímica", "AgroCenter {fant}"))
T(C, P, "Fertilizantes foliares e micronutrientes", "pj", "venda de fertilizantes foliares",
  "litro", 40, 160, "regional",
  ["boro", "zinco", "manganês", "cálcio foliar", "aminoácidos", "bioestimulantes"],
  ["Vende foliares com boro, zinco e manganês para o cafeeiro.",
   "Oferece bioestimulantes para pré-florada e enchimento de grãos.",
   "Tem técnico para acompanhar os resultados."],
  nomes_pj=("{fant} Nutrição Vegetal", "{sob} Foliares"))
T(C, P, "Adubos orgânicos", "mix", "venda de adubos orgânicos", "tonelada", 250, 900, "local",
  ["esterco bovino", "cama de frango", "composto orgânico", "palha de café", "torta de mamona"],
  ["Vende cama de frango, esterco curtido e composto orgânico.",
   "Faz entrega a granel com caminhão basculante.",
   "Fornece material para lavouras orgânicas e convencionais."],
  nomes_pj=("{fant} Orgânicos", "{sob} Adubos Orgânicos"))
T(C, P, "Bioinsumos e controle biológico", "pj", "venda de bioinsumos", "litro", 60, 250, "nacional",
  ["Beauveria bassiana", "Trichoderma", "Bacillus", "fungos entomopatogênicos",
   "controle biológico da broca"],
  ["Vende produtos biológicos para controle de broca e nematoides.",
   "Tem linhas à base de Trichoderma e Bacillus para saúde do solo.",
   "Dá suporte técnico para integrar biológicos ao manejo químico."],
  nomes_pj=("Bio{fant}", "{fant} Biológicos"))

C = "Mudas e sementes"
T(C, P, "Viveiro de mudas de café", "mix", "viveiro de mudas de café", "muda", 1.2, 3.5, "regional",
  ["Catuaí Vermelho", "Catuaí Amarelo", "Mundo Novo", "Arara", "Topázio", "Catucaí", "conilon clonal",
   "mudas enxertadas"],
  ["Produz mudas de café em tubete e saquinho com registro no RENASEM.",
   "Trabalha com cultivares resistentes à ferrugem.",
   "Faz mudas por encomenda com prazo de produção combinado."],
  certs=("Registro RENASEM",), n=(7, 9),
  nomes_pj=("Viveiro {fant}", "{sob} Mudas de Café"))
T(C, P, "Sementes de adubação verde", "pj", "venda de sementes para adubação verde", "kg", 12, 45,
  "nacional",
  ["braquiária", "crotalária", "feijão-de-porco", "mucuna", "milheto", "mix de cobertura"],
  ["Vende sementes para cobertura nas entrelinhas do café.",
   "Tem mixes prontos para melhorar a estrutura do solo.",
   "Envia sementes pelo correio ou transportadora."],
  nomes_pj=("{fant} Sementes", "{sob} Sementes"))

C = "Máquinas e implementos"
T(C, P, "Concessionária de tratores cafeeiros", "pj", "concessionária de tratores", "unidade",
  180000, 450000, "regional",
  ["tratores estreitos", "tratores cafeeiros", "financiamento", "assistência técnica", "peças originais"],
  ["Vende tratores estreitos próprios para as entrelinhas do café.",
   "Tem oficina própria e assistência técnica no campo.",
   "Auxilia no financiamento por linhas de crédito rural."],
  nomes_pj=("{fant} Tratores", "{sob} Máquinas Agrícolas"))
T(C, P, "Revenda de colhedoras de café", "pj", "revenda de colhedoras de café", "unidade",
  700000, 1900000, "regional",
  ["colhedora automotriz", "colhedora tracionada", "recolhedora", "colhedoras seminovas"],
  ["Vende colhedoras automotrizes e tracionadas para café.",
   "Tem equipe de pós-venda e treinamento de operador.",
   "Trabalha com consórcio e financiamento."],
  n=(3, 5), nomes_pj=("{fant} Colhedoras", "{sob} Máquinas para Café"))
T(C, P, "Derriçadeiras e roçadeiras portáteis", "pj", "venda de derriçadeiras e roçadeiras",
  "unidade", 2200, 5500, "regional",
  ["derriçadeira a gasolina", "derriçadeira elétrica a bateria", "roçadeira", "peças e hastes",
   "assistência técnica"],
  ["Vende derriçadeiras a gasolina e elétricas a bateria.",
   "Tem assistência técnica e peças de reposição na loja.",
   "Faz revisão pré-safra das máquinas."],
  nomes_pj=("{fant} Motopeças", "{sob} Equipamentos Agrícolas"))
T(C, P, "Revenda de pulverizadores", "pj", "revenda de pulverizadores", "unidade", 3500, 95000,
  "regional",
  ["pulverizador costal", "turbo-atomizador", "pulverizador de barra", "bicos e peças"],
  ["Vende pulverizadores costais e turbo-atomizadores para café.",
   "Faz calibração e regulagem na entrega.",
   "Tem bicos e peças de reposição."],
  nomes_pj=("{fant} Pulverizadores", "{sob} Agrícola"))
T(C, P, "Implementos agrícolas", "pj", "venda de implementos agrícolas", "unidade", 12000, 90000,
  "regional",
  ["roçadeira tratorizada", "adubadeira", "trincha", "recolhedora", "esparramadeira de palha",
   "carretas"],
  ["Vende roçadeiras, adubadeiras e trinchas para lavouras de café.",
   "Tem implementos para o recolhimento e a esparramação de palha.",
   "Entrega e faz o engate do implemento."],
  nomes_pj=("{fant} Implementos", "{sob} Implementos Agrícolas"))
T(C, P, "Máquinas agrícolas usadas", "mix", "venda de máquinas agrícolas usadas", "unidade",
  40000, 350000, "regional",
  ["tratores usados", "colhedoras usadas", "implementos usados", "troca e consignação"],
  ["Vende tratores, colhedoras e implementos usados revisados.",
   "Aceita troca e trabalha com consignação.",
   "Faz a vistoria da máquina antes da venda."],
  nomes_pj=("{fant} Seminovos Agrícolas", "{sob} Máquinas Usadas"))
T(C, P, "Peças para máquinas agrícolas", "pj", "loja de peças para máquinas agrícolas",
  "ticket médio", 300, 1500, "regional",
  ["peças de trator", "peças de colhedora", "rolamentos", "correias", "mangueiras hidráulicas"],
  ["Vende peças para tratores, colhedoras e implementos.",
   "Monta mangueiras hidráulicas na hora.",
   "Faz entrega rápida na safra."],
  nomes_pj=("{fant} Peças Agrícolas", "{sob} Autopeças Rural"))

C = "Pós-colheita e beneficiamento (equipamentos)"
T(C, P, "Secadores de café", "pj", "venda de secadores de café", "unidade", 60000, 250000, "nacional",
  ["secador rotativo", "secador de leito fixo", "secador vertical", "fornalha", "instalação"],
  ["Fabrica e instala secadores rotativos e de leito fixo.",
   "Dimensiona o secador de acordo com a produção da fazenda.",
   "Oferece assistência técnica e peças."],
  nomes_pj=("{fant} Secadores", "{sob} Equipamentos para Café"))
T(C, P, "Lavadores e despolpadores", "pj", "venda de lavadores e despolpadores", "unidade", 35000,
  180000, "nacional",
  ["lavador", "descascador de cereja", "despolpador", "desmucilador", "tanques de fermentação"],
  ["Vende lavadores e descascadores para produção de cereja descascado.",
   "Tem tanques para fermentação controlada.",
   "Faz a instalação e treinamento do operador."],
  nomes_pj=("{fant} Máquinas Pós-Colheita", "{sob} Lavadores"))
T(C, P, "Máquinas de beneficiamento", "pj", "venda de máquinas de beneficiamento", "unidade",
  80000, 400000, "nacional",
  ["descascador de café seco", "peneira classificadora", "catadora eletrônica", "mesa densimétrica",
   "elevadores"],
  ["Vende linhas completas de beneficiamento para fazendas e armazéns.",
   "Tem catadoras eletrônicas e mesas densimétricas.",
   "Faz o projeto da unidade de beneficiamento."],
  nomes_pj=("{fant} Beneficiadoras", "{sob} Máquinas de Beneficiamento"))
T(C, P, "Lenha, cavaco e pellets para secagem", "mix", "venda de lenha e biomassa para secagem", "m³",
  90, 220, "local",
  ["lenha de eucalipto", "cavaco", "pellets", "entrega a granel"],
  ["Vende lenha de eucalipto de reflorestamento para fornalhas.",
   "Fornece cavaco e pellets para secadores automatizados.",
   "Faz entrega programada durante a safra."],
  nomes_pj=("{fant} Lenha e Biomassa", "{sob} Florestal"))
T(C, P, "Lonas para terreiro e secagem", "pj", "venda de lonas para secagem de café", "m²", 4, 12,
  "nacional",
  ["lona de terreiro", "lona para cobertura", "tela de terreiro suspenso", "lona sob medida"],
  ["Vende lonas para secagem e cobertura do café no terreiro.",
   "Faz lonas sob medida com ilhós.",
   "Tem telas para terreiros suspensos."],
  nomes_pj=("{fant} Lonas", "{sob} Lonas e Coberturas"))

C = "Irrigação e infraestrutura"
T(C, P, "Sistemas de irrigação", "pj", "venda de sistemas de irrigação", "hectare", 12000, 25000,
  "regional",
  ["gotejamento", "tubos gotejadores", "bombas", "filtros", "automação", "fertirrigação"],
  ["Vende e instala sistemas de gotejamento para café.",
   "Tem bombas, filtros e automação de irrigação.",
   "Faz o projeto sem custo na compra do sistema."],
  n=(5, 7), nomes_pj=("{fant} Irrigação", "{sob} Irrigação"))
T(C, P, "Materiais para construção rural", "pj", "loja de materiais para construção rural",
  "ticket médio", 1500, 15000, "local",
  ["cimento", "telhas", "arame e mourões", "madeira", "estruturas metálicas"],
  ["Vende materiais para terreiros, tulhas e galpões.",
   "Tem arame, mourões e material para cercas.",
   "Faz entrega na propriedade."],
  nomes_pj=("{fant} Materiais de Construção", "{sob} Materiais Rurais"))
T(C, P, "Energia solar rural", "pj", "venda e instalação de energia solar", "kWp", 3500, 5500,
  "regional",
  ["energia solar fotovoltaica", "bombeamento solar", "financiamento", "homologação"],
  ["Instala sistemas solares para reduzir a conta de energia de secadores e bombas.",
   "Faz o projeto e a homologação junto à distribuidora.",
   "Trabalha com linhas de financiamento rural."],
  nomes_pj=("{fant} Solar", "{sob} Energia Solar"))
T(C, P, "Caixas d'água e reservatórios", "pj", "venda de caixas d'água e reservatórios", "unidade",
  800, 12000, "regional",
  ["caixas d'água", "tanques de polietileno", "reservatórios para pulverização", "cisternas"],
  ["Vende caixas d'água e tanques para calda de pulverização.",
   "Tem reservatórios de grande volume para irrigação.",
   "Faz entrega na propriedade."],
  nomes_pj=("{fant} Reservatórios", "{sob} Tanques"))

C = "Colheita e armazenagem (materiais)"
T(C, P, "Panos e ferramentas de colheita", "pj", "venda de materiais para colheita", "unidade", 60,
  250, "regional",
  ["pano de colheita", "peneira", "rastelo", "balaio", "medida de 60 L"],
  ["Vende panos de colheita, peneiras e rastelos.",
   "Tem kits completos para turmas de colheita.",
   "Faz entrega antes da safra."],
  nomes_pj=("{fant} Artigos Rurais", "{sob} Casa do Produtor"))
T(C, P, "Sacaria", "pj", "venda de sacaria para café", "unidade", 8, 60, "nacional",
  ["sacos de juta", "sacos de ráfia", "big bags", "sacaria personalizada"],
  ["Vende sacos de juta e ráfia para café beneficiado.",
   "Tem big bags para armazenagem de café em coco.",
   "Faz sacaria personalizada com a marca da fazenda."],
  nomes_pj=("{fant} Sacaria", "{sob} Embalagens"))
T(C, P, "Embalagens herméticas para café", "pj", "venda de embalagens herméticas", "unidade", 25, 45,
  "nacional",
  ["sacos herméticos multicamada", "preservação de cafés especiais", "embalagem para exportação"],
  ["Vende sacos herméticos que preservam a qualidade de cafés especiais.",
   "Atende produtores que exportam microlotes.",
   "Envia para todo o Brasil."],
  nomes_pj=("{fant} Embalagens", "Hermetic {fant}"))

C = "EPI e ferramentas"
T(C, P, "Equipamentos de proteção individual (EPI)", "pj", "loja de EPI", "kit", 180, 450,
  "regional",
  ["kit de aplicação", "máscaras", "luvas", "botas", "protetor auricular", "óculos"],
  ["Vende kits completos de EPI para aplicação de defensivos.",
   "Tem EPI para operadores de máquinas e motosserra.",
   "Emite certificados de aprovação (CA) dos produtos."],
  nomes_pj=("{fant} EPI", "{sob} Segurança do Trabalho"))
T(C, P, "Ferramentas manuais", "pj", "loja de ferramentas rurais", "unidade", 40, 200, "local",
  ["enxada", "foice", "serrote de poda", "tesoura de poda", "motosserra"],
  ["Vende ferramentas para capina e poda.",
   "Tem motosserras e peças.",
   "Atende produtores e turmas de trabalho."],
  nomes_pj=("{fant} Ferragens", "{sob} Ferramentas"))

C = "Tecnologia e comercialização"
T(C, P, "Estações meteorológicas e sensores", "pj", "venda de estações meteorológicas e sensores",
  "unidade", 3000, 18000, "nacional",
  ["estação meteorológica", "sensor de umidade do solo", "pluviômetro digital",
   "alerta de geada", "monitoramento remoto"],
  ["Vende estações meteorológicas conectadas ao celular.",
   "Tem sensores de umidade do solo para manejo de irrigação.",
   "Envia alertas de geada e chuva."],
  nomes_pj=("{fant} Agrotech", "Clima{fant}"))
T(C, P, "Software de gestão rural", "pj", "software de gestão rural", "mês", 90, 600, "nacional",
  ["gestão financeira", "controle de safra", "estoque de insumos", "rastreabilidade",
   "aplicativo móvel"],
  ["Oferece sistema para controlar custos, estoque e produção da fazenda.",
   "Tem aplicativo para registro de atividades no campo.",
   "Gera relatórios de custo por saca."],
  nomes_pj=("{fant} Agro Software", "Fazenda{fant} App"))
T(C, P, "Medidores de umidade de grãos", "pj", "venda de medidores de umidade", "unidade", 1800,
  7000, "nacional",
  ["medidor de umidade", "determinador de umidade", "calibração", "termômetro de massa"],
  ["Vende medidores para controlar o ponto de secagem do café.",
   "Faz calibração e assistência técnica.",
   "Envia para todo o Brasil."],
  nomes_pj=("{fant} Instrumentos", "{sob} Medidores"))
T(C, P, "Equipamentos de classificação e prova", "pj", "venda de equipamentos de classificação e prova",
  "unidade", 900, 25000, "nacional",
  ["peneiras de classificação", "mesa de prova", "mini torrador", "moedor de prova",
   "kit de classificação"],
  ["Vende peneiras, mesas de prova e mini torradores para amostra.",
   "Monta salas de prova para fazendas e cooperativas.",
   "Oferece treinamento básico de classificação."],
  nomes_pj=("{fant} Equipamentos de Prova", "{sob} Laboratório de Café"))
T(C, P, "Cooperativa cafeeira", "pj", "cooperativa cafeeira", "cota-parte de adesão", 500, 3000,
  "regional",
  ["compra de café", "venda de insumos", "armazenagem", "assistência técnica", "crédito ao cooperado"],
  ["Compra o café do cooperado e vende insumos com preço de cooperativa.",
   "Oferece assistência técnica e armazenagem.",
   "Tem linhas de crédito para cooperados."],
  n=(5, 6), nomes_pj=("Cooperativa {fant}", "Coop{fant}"))


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
def fmt_brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def arredonda_preco(v):
    if v >= 10000:
        return round(v, -3)
    if v >= 1000:
        return round(v, -1)
    if v >= 50:
        return round(v)
    return round(v, 2)


def gera_avaliacao():
    r = random.random()
    if r < 0.08:
        return round(random.uniform(2.3, 3.4), 1)
    if r < 0.35:
        return round(random.uniform(3.5, 4.2), 1)
    return round(random.uniform(4.3, 5.0), 1)


def gera_telefone(ddd):
    return f"({ddd}) 9{random.randint(8000, 9999)}-{random.randint(1000, 9999)}"


nomes_usados = set()


def gera_nome(t, natureza, cidade):
    for tentativa in range(60):
        if natureza == "pessoa_fisica":
            n = nome_pessoa()
        else:
            tpl = random.choice(t["nomes_pj"])
            n = tpl.format(sob=random.choice(SOBRENOMES), fant=random.choice(FANTASIA),
                           cid=cidade, tipo=t["tipo"])
            if tentativa >= 30:                 # combinações esgotando: vira "filial" da cidade
                n = f"{n} {cidade}"
        if n not in nomes_usados:
            nomes_usados.add(n)
            return n
    raise RuntimeError("não foi possível gerar nome único")


# Papel usado na descrição de pessoa física quando o "papel" do tipo descreve um ramo
PAPEL_PF = {
    "Engenheiro agrônomo": "engenheiro(a) agrônomo(a) em cafeicultura",
    "Adubos orgânicos": "produtor(a) e vendedor(a) de adubos orgânicos",
    "Viveiro de mudas de café": "viveirista de mudas de café",
    "Máquinas agrícolas usadas": "revendedor(a) autônomo(a) de máquinas agrícolas usadas",
    "Lenha, cavaco e pellets para secagem": "fornecedor(a) de lenha e biomassa para secagem",
}


# Frases genéricas (sorteadas além das do tipo) para as descrições não ficarem repetitivas
FRASES_SERVICO = [
    "Emite nota fiscal e formaliza o serviço em contrato.",
    "Atende pequenos, médios e grandes produtores.",
    "Faz orçamento sem compromisso na propriedade.",
    "Aceita pagamento via Pix, transferência ou parcelado até a colheita.",
    "Trabalha aos sábados durante a safra.",
    "Tem equipe treinada e equipamentos revisados.",
    "Tem referências de produtores da região.",
    "Segue as boas práticas exigidas por certificadoras.",
    "Agenda as visitas com antecedência e cumpre os prazos combinados.",
    "Prioriza atendimento a propriedades familiares.",
]
FRASES_PRODUTO = [
    "Emite nota fiscal e entrega na propriedade.",
    "Parcela no cartão ou aceita pagamento na safra.",
    "Trabalha com marcas reconhecidas e garantia de fábrica.",
    "Dá desconto em compras de volume e para cooperados.",
    "Tem assistência técnica e pós-venda.",
    "Mantém estoque o ano todo.",
    "Faz orçamento rápido pela plataforma.",
    "Atende de pequenos produtores a grandes fazendas.",
    "Oferece condições especiais antes da safra.",
]

DISP_SERV = [("imediata", 4), ("sob agendamento", 5), ("agenda cheia até o fim da safra", 1)]
DISP_PROD = [("pronta entrega", 6), ("sob encomenda", 3), ("estoque limitado", 1)]


def escolhe(pares):
    itens, pesos = zip(*pares)
    return random.choices(itens, weights=pesos)[0]


def regioes_para_tipo(n):
    """1ª volta sem repetição (garante o tipo em todas as regiões possíveis);
    o restante segue o peso real de cada região (Sul de Minas tem bem mais fornecedores que o Oeste da Bahia)."""
    escolhidas, disp = [], dict(PESOS_REGIAO)
    while len(escolhidas) < n and disp:
        r = random.choices(list(disp), weights=list(disp.values()))[0]
        del disp[r]
        escolhidas.append(r)
    faltam = n - len(escolhidas)
    if faltam > 0:
        escolhidas += random.choices(list(PESOS_REGIAO), weights=list(PESOS_REGIAO.values()), k=faltam)
    return escolhidas


def gera_registro(t, regiao):
    uf, ddd, cidades = REGIOES[regiao]
    cidade = random.choice(cidades)

    if t["nat"] == "pf":
        natureza = "pessoa_fisica"
    elif t["nat"] == "pj":
        natureza = "empresa"
    else:
        natureza = random.choice(["pessoa_fisica", "empresa"])

    abr = t["abr"]
    if abr == "local" and natureza == "empresa" and random.random() < 0.4:
        abr = "regional"
    if abr == "nacional" and natureza == "pessoa_fisica" and random.random() < 0.5:
        abr = "regional"

    if abr == "local":
        outras = [c for c in cidades if c != cidade]
        atendidas = [cidade] + random.sample(outras, k=min(len(outras), random.randint(1, 3)))
        raio = random.choice([20, 30, 40, 50, 60])
        txt_atend = f"Atende produtores em {', '.join(atendidas)}, num raio de até {raio} km."
        cidades_atendidas = ", ".join(atendidas)
    elif abr == "regional":
        raio = random.choice([80, 100, 120, 150, 200])
        cidades_atendidas = ", ".join(cidades)
        txt_atend = (f"Atende toda a região {regiao} ({', '.join(cidades)}), "
                     f"num raio de até {raio} km da sede.")
    else:
        raio = None
        cidades_atendidas = "Todo o Brasil"
        txt_atend = "Atende e envia para todo o Brasil."

    nome = gera_nome(t, natureza, cidade)
    anos = random.randint(1, 35) if natureza == "pessoa_fisica" else random.randint(2, 45)
    esp = random.sample(t["esp"], k=min(len(t["esp"]), random.randint(2, 4)))
    frases = random.sample(t["frases"], k=min(len(t["frases"]), 2))
    genericas = FRASES_SERVICO if t["tipo_cadastro"] == "servico" else FRASES_PRODUTO
    frases += random.sample(genericas, k=random.choice([0, 1, 1, 2]))
    certs = []
    if t["certs"]:
        certs = random.sample(list(t["certs"]), k=random.randint(0, len(t["certs"])))
        if not certs and random.random() < 0.7:
            certs = [t["certs"][0]]

    preco = arredonda_preco(random.uniform(t["pmin"], t["pmax"]))
    aval = gera_avaliacao()
    total_aval = random.randint(3, 40) if natureza == "pessoa_fisica" else random.randint(10, 400)
    disp = escolhe(DISP_SERV if t["tipo_cadastro"] == "servico" else DISP_PROD)

    if natureza == "pessoa_fisica":
        papel = PAPEL_PF.get(t["tipo"], t["papel"])
        abertura = (f"{nome} atua como {papel} em {cidade}/{uf}, na região {regiao}, "
                    f"com {anos} anos de experiência.")
    else:
        abertura = (f"{nome} é uma empresa sediada em {cidade}/{uf}, na região {regiao}, "
                    f"no mercado há {anos} anos. Segmento: {t['tipo']}.")

    extras = []
    if regiao in REGIOES_CONILON and t["categoria"] not in ("Gestão, certificação e serviços de apoio",):
        extras.append("Tem experiência com café conilon/robusta.")
    elif regiao in REGIOES_MECANIZADAS and t["tipo"] in (
            "Serviço de colheita mecanizada", "Revenda de colhedoras de café",
            "Concessionária de tratores cafeeiros", "Aplicador de defensivos"):
        extras.append("Acostumado a lavouras planas e altamente mecanizadas.")
    elif regiao in REGIOES_ESPECIAIS and "cafés especiais" in " ".join(t["esp"]).lower() \
            and random.random() < 0.5:
        extras.append("Atende muitos produtores de cafés especiais da região.")

    if "%" in t["unidade"]:
        txt_preco = f"Cobra em média {str(preco).replace('.', ',')}% ({t['unidade']})."
    else:
        txt_preco = f"Preço médio: {fmt_brl(preco)} por {t['unidade']}."

    partes = [abertura, *frases, *extras,
              f"Especialidades: {', '.join(esp)}.",
              txt_atend, txt_preco,
              f"Avaliação média {str(aval).replace('.', ',')} de 5 ({total_aval} avaliações).",
              f"Disponibilidade: {disp}."]
    if certs:
        partes.append(f"Certificações/registros: {', '.join(certs)}.")
    descricao = " ".join(partes)

    return dict(
        tipo_cadastro=t["tipo_cadastro"], categoria=t["categoria"], tipo=t["tipo"],
        nome=nome, natureza=natureza, descricao=descricao, especialidades=", ".join(esp),
        avaliacao=aval, total_avaliacoes=total_aval, preco_medio=preco,
        unidade_preco=t["unidade"], cidade_sede=cidade, uf=uf, regiao=regiao,
        abrangencia=abr, cidades_atendidas=cidades_atendidas, raio_atendimento_km=raio,
        anos_experiencia=anos, certificacoes=", ".join(certs) if certs else None,
        disponibilidade=disp, telefone=gera_telefone(ddd), ativo=1 if random.random() > 0.04 else 0,
    )


def alocar(total):
    """Distribui o total entre os tipos proporcionalmente ao peso (ponto médio de n) de cada tipo."""
    pesos = [(a + b) / 2 for a, b in (t["n"] for t in TIPOS)]
    soma = sum(pesos)
    brutos = [total * p / soma for p in pesos]
    qtd = [max(2, int(x)) for x in brutos]
    # distribui o que faltar pelos maiores restos
    restos = sorted(range(len(TIPOS)), key=lambda i: brutos[i] - int(brutos[i]), reverse=True)
    i = 0
    while sum(qtd) < total:
        qtd[restos[i % len(restos)]] += 1
        i += 1
    return qtd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())

    registros = []
    for t, n in zip(TIPOS, alocar(args.total)):
        for regiao in regioes_para_tipo(n):
            registros.append(gera_registro(t, regiao))
    random.shuffle(registros)

    cols = list(registros[0].keys())
    sql = f"INSERT INTO fornecedores ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    con.executemany(sql, [tuple(r[c] for c in cols) for r in registros])
    con.commit()

    with open(DUMP_PATH, "w", encoding="utf-8") as f:
        for linha in con.iterdump():
            f.write(linha + "\n")

    total = con.execute("SELECT COUNT(*) FROM fornecedores").fetchone()[0]
    print(f"{total} registros | {len(TIPOS)} tipos")
    for row in con.execute("SELECT tipo_cadastro, COUNT(*) FROM fornecedores GROUP BY 1"):
        print(row)
    for row in con.execute("SELECT regiao, COUNT(*) FROM fornecedores GROUP BY 1 ORDER BY 2 DESC"):
        print(row)
    con.close()


if __name__ == "__main__":
    main()
