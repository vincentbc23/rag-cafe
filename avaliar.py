"""
Avaliação da busca híbrida com perguntas de teste.

Métricas:
  Hit@1  -> o 1º resultado é de um tipo esperado
  P@3    -> fração dos 3 primeiros que são de um tipo esperado (os 3 que podem virar botões)
  Hit@5  -> há pelo menos um tipo esperado entre os 5 enviados ao LLM (ele tem como acertar)
  Local  -> entre os resultados certos, fração dentro da área pedida (perguntas com local)

Uso:
    python avaliar.py            # resumo
    python avaliar.py -v         # mostra os erros
"""
import argparse

from busca import Buscador

CASOS = [
    ("preciso de um agrônomo para fazer a recomendação de adubação da minha lavoura em Patrocínio",
     {"Engenheiro agrônomo"}),
    ("quero contratar gente para colher café em Três Pontas",
     {"Colhedor manual", "Empreiteiro de mão de obra rural", "Operador de derriçadeira"}),
    ("onde compro adubo no sul de minas",
     {"Revenda de fertilizantes e corretivos", "Adubos orgânicos",
      "Fertilizantes foliares e micronutrientes", "Cooperativa cafeeira"}),
    ("alguém para fazer a poda de esqueletamento no cafezal", {"Equipe de poda"}),
    ("quero mudas de catuaí para plantar em Manhuaçu", {"Viveiro de mudas de café"}),
    ("preciso avaliar a qualidade do meu café para vender como especial",
     {"Q-Grader / provador de café", "Classificador de café", "Consultor de cafés especiais"}),
    ("pulverização com drone em lavoura de montanha", {"Piloto de drone agrícola"}),
    ("quero instalar irrigação por gotejamento em Franca",
     {"Projetista de irrigação", "Sistemas de irrigação"}),
    ("meu secador quebrou, preciso de alguém para consertar",
     {"Técnico de manutenção de secadores e beneficiadoras", "Mecânico de máquinas agrícolas"}),
    ("comprar uma colhedora de café", {"Revenda de colhedoras de café", "Máquinas agrícolas usadas"}),
    ("terceirizar a colheita mecanizada no cerrado mineiro", {"Serviço de colheita mecanizada"}),
    ("preciso tirar o CAR e a outorga de água da fazenda",
     {"Engenheiro ambiental", "Projetista de irrigação"}),
    ("análise de solo em Lavras",
     {"Laboratório de análise de solo e foliar", "Técnico agrícola", "Engenheiro agrônomo"}),
    ("certificação Rainforest Alliance para minha fazenda", {"Consultor de certificações"}),
    ("controle da broca do café",
     {"Consultor em manejo de pragas e doenças", "Bioinsumos e controle biológico",
      "Aplicador de defensivos", "Revenda de defensivos agrícolas"}),
    ("lenha para a fornalha do secador em Venda Nova do Imigrante",
     {"Lenha, cavaco e pellets para secagem"}),
    ("sacos de juta para ensacar o café", {"Sacaria"}),
    ("financiamento pelo Pronaf", {"Consultor de crédito rural"}),
    ("contador para fazer o imposto de renda do produtor rural", {"Contador rural"}),
    ("construir um terreiro de concreto",
     {"Construtor de terreiros e tulhas", "Materiais para construção rural"}),
    ("EPI para aplicação de agrotóxico", {"Equipamentos de proteção individual (EPI)"}),
    ("quero vender meu café, preciso de um corretor na Mogiana",
     {"Corretor de café", "Cooperativa cafeeira"}),
    ("torrar meu café e vender com minha marca própria", {"Torrefação por encomenda"}),
    ("diarista para capina e roçada em Caratinga", {"Trabalhador rural para tratos culturais"}),
    ("prova de xícara e pontuação SCA", {"Q-Grader / provador de café"}),
    ("trator estreito para café no Paraná", {"Concessionária de tratores cafeeiros",
                                              "Máquinas agrícolas usadas"}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", action="store_true")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    b = Buscador()
    hits, precs, hits5, locs = [], [], [], []
    for pergunta, esperados in CASOS:
        it, res = b.buscar(pergunta, args.k)
        tipos = [r["tipo"] for r in res]
        hit = bool(tipos) and tipos[0] in esperados
        prec = sum(t in esperados for t in tipos[:3]) / 3
        hit5 = any(t in esperados for t in tipos)
        tem_local = bool(it["cidades"] or it["regioes"] or it["ufs"])
        # entre os resultados CORRETOS, quantos estão na área pedida
        certos = [r for r in res if r["tipo"] in esperados]
        loc = (sum(not r["fora_da_area"] for r in certos) / len(certos)) if (tem_local and certos) else 1.0
        hits.append(hit); precs.append(prec); hits5.append(hit5); locs.append(loc)
        if args.v and (not hit or prec < 0.6 or not hit5):
            print(f"✗ {pergunta}\n  termos={it['termos']} local={it['cidades'] or it['regioes'] or it['ufs']}")
            for r in res:
                ok = "✓" if r["tipo"] in esperados else " "
                print(f"   {ok} {r['tipo']} | {r['nome']} | {r['cidade_sede']} | local={r['nivel_local']}")
    n = len(CASOS)
    print(f"\n{n} perguntas | Hit@1 = {sum(hits)/n:.0%} | P@3 = {sum(precs)/n:.0%} | "
          f"Hit@{args.k} = {sum(hits5)/n:.0%} | Certos dentro da área = {sum(locs)/n:.0%}")


if __name__ == "__main__":
    main()
