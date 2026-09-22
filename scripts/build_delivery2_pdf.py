from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "pdf" / "projeto-entrega2.pdf"
FIGS = ROOT / "docs" / "figs"

NAVY = colors.HexColor("#15324A")
BLUE = colors.HexColor("#2B6F9C")
TEAL = colors.HexColor("#1B8A89")
LIGHT = colors.HexColor("#EAF2F7")
MUTED = colors.HexColor("#5F6B73")
RED = colors.HexColor("#B54242")


def load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=NAVY, alignment=TA_CENTER, spaceAfter=18))
styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontName="Helvetica", fontSize=13, leading=18, textColor=BLUE, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceBefore=8, spaceAfter=12))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=BLUE, spaceBefore=10, spaceAfter=7))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.4, leading=13.4, alignment=TA_JUSTIFY, textColor=colors.HexColor("#25313A"), spaceAfter=7))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.7, leading=10.2, textColor=MUTED, spaceAfter=4))
styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.7, leading=10.2, textColor=colors.white, spaceAfter=0))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10.2, leading=14, textColor=NAVY, backColor=LIGHT, borderColor=TEAL, borderWidth=0.8, borderPadding=10, spaceBefore=8, spaceAfter=10))


def P(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def bullets(items: list[str]):
    return [P(f"&#8226;&nbsp; {item}") for item in items]


def styled_table(data, widths, *, font_size=7.6, header=True):
    cooked = []
    for row_index, row in enumerate(data):
        style_name = "TableHeader" if header and row_index == 0 else "Smallx"
        cooked.append([[P(str(cell), style_name)][0] for cell in row])
    table = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C6CF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    table.setStyle(TableStyle(commands))
    return table


def chart(path: Path, width=16.2 * cm):
    image = Image(str(path))
    ratio = image.imageHeight / image.imageWidth
    image.drawWidth = width
    image.drawHeight = width * ratio
    return image


def page_frame(canvas, doc):
    canvas.saveState()
    width, height = A4
    if doc.page > 1:
        canvas.setStrokeColor(colors.HexColor("#C7D4DC"))
        canvas.line(1.8 * cm, height - 1.45 * cm, width - 1.8 * cm, height - 1.45 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.8 * cm, height - 1.15 * cm, "Agente Autônomo para Análise de Editais - Entrega 2")
        canvas.drawRightString(width - 1.8 * cm, 1.0 * cm, f"Página {doc.page}")
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    hypothesis = load_json("evaluation/results/hypothesis_report.json")
    comparison = load_json("evaluation/results/final_comparison.json")["summary"]
    errors = load_json("evaluation/results/error_analysis.json")
    selected = load_json("evaluation/results/selected_config.json")
    by_approach = {item["approach"]: item for item in comparison}
    rag = by_approach["rag"]
    regex = by_approach["regex"]
    llm = by_approach["llm_no_retrieval"]

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm,
        topMargin=1.8 * cm, bottomMargin=1.55 * cm,
        title="Agente Autônomo para Análise de Editais de Licitação - Entrega 2",
        author="Danielle Ballester; Carol Guzman; André Araújo; David Damasceno; Raylson Lima",
    )
    story = []
    story += [Spacer(1, 3.0 * cm), P("AGENTE AUTÔNOMO PARA ANÁLISE DE EDITAIS DE LICITAÇÃO", "CoverTitle"), HRFlowable(width="55%", thickness=2, color=TEAL, spaceBefore=4, spaceAfter=18), P("Entrega 2 - Relatório final de implementação e avaliação", "CoverSub"), Spacer(1, 1.0 * cm), P("MVP RAG com evidências, benchmark humano e avaliação RAGAS", "CoverSub"), Spacer(1, 3.0 * cm), P("Danielle Magalhães Ballester<br/>Carol Anely Miranda Guzman<br/>André Joás Lima de Araújo<br/>David Damasceno da Frota<br/>Raylson Silva de Lima", "CoverSub"), Spacer(1, 2.0 * cm), P("22 de julho de 2026", "CoverSub"), PageBreak()]

    story += [P("Resumo executivo", "H1x"), P("Foi concluído um MVP para extração rastreável de informações críticas de editais, com Flask, PyMuPDF, OCR, embeddings MiniLM, FAISS, respostas estruturadas, evidências literais e um FunctionAgent real do LlamaIndex."), P("O benchmark contém 10 editais e 30 referências humanas validadas. Foram executadas 12 configurações RAG no desenvolvimento, com seleção exclusiva nesse split. O teste final foi aberto somente depois do congelamento por hash."), P(f"Resultado principal: Faithfulness <b>{hypothesis['observed']['faithfulness']['mean']:.2f}</b>, Answer Correctness <b>{hypothesis['observed']['answer_correctness']['mean']:.4f}</b> e alucinação <b>{hypothesis['observed']['hallucination_rate']:.0%}</b>. A hipótese foi <b>parcialmente confirmada</b>.", "Callout"), P("A cobertura do RAG foi 2/9 campos. Essa limitação é central: as médias RAGAS descrevem somente as respostas existentes e não compensam os sete campos sem resposta."), P("Equipe e responsabilidades", "H2x"), styled_table([["Integrante", "Papel", "Contribuição consolidada"], ["Danielle Magalhães Ballester", "Liderança, documentação e apresentação", "Coordenação e narrativa"], ["Carol Anely Miranda Guzman", "Dados", "Organização e qualidade dos dados"], ["André Joás Lima de Araújo", "Engenharia e modelagem", "Pipeline, indexação e agente"], ["David Damasceno da Frota", "Avaliação", "Benchmark, métricas e erros"], ["Raylson Silva de Lima", "Reprodutibilidade", "Ambiente, testes e execução"]], [4.4*cm, 4.5*cm, 7.0*cm]), PageBreak()]

    story += [P("1. Problema, hipótese e objetivos", "H1x"), P("Editais são longos, heterogêneos e distribuem informações críticas entre texto principal e anexos. A análise manual é custosa e sujeita a falhas; LLMs sem fonte podem alucinar. O projeto investiga se RAG consegue combinar extração estruturada e rastreabilidade."), P("Pergunta de pesquisa", "H2x"), P("Em que medida um agente baseado em RAG consegue extrair prazo, valor estimado e modalidade com Faithfulness >= 0,85, Answer Correctness >= 0,80 e alucinação <= 10%?"), P("Hipótese", "H2x"), P("Os três limiares seriam alcançados no conjunto de teste."), P("Objetivos realizados", "H2x")] + bullets(["Pipeline PDF/OCR, chunking, embeddings e FAISS.", "Extração estruturada com evidência literal e página.", "Benchmark humano com desenvolvimento/teste isolados.", "Comparação com regex e LLM sem recuperação.", "Métricas RAGAS, custo, tokens, latência, gráficos e análise de erros.", "FunctionAgent real e conector opcional para a API pública do PNCP."])

    story += [P("2. Arquitetura e implementação", "H1x"), P("Fluxo técnico", "H2x"), P("PDF -> validação -> extração PyMuPDF/OCR -> chunking -> embeddings MiniLM -> FAISS -> recuperação por document_id -> LLM -> JSON estruturado -> validação de evidência -> aplicação/agent."), styled_table([["Camada", "Implementação", "Controle de qualidade"], ["Entrada", "Upload Flask e coleta PNCP opcional", "Assinatura PDF, tamanho, SHA-256"], ["Documento", "PyMuPDF e Tesseract", "Fallback OCR e páginas preservadas"], ["Recuperação", "MiniLM + FAISS", "Filtro obrigatório por document_id"], ["Geração", "Groq openai/gpt-oss-120b", "Temperatura 0 e JSON estruturado"], ["Evidência", "Página, chunk e trecho", "Validação literal e normalização"], ["Agente", "LlamaIndex FunctionAgent", "Ferramenta tipada e top-k limitado"]], [3.0*cm, 6.0*cm, 6.9*cm]), P("O FunctionAgent está disponível na aplicação. O experimento mede diretamente seu núcleo RAG/extrator para evitar chamadas de orquestração diferentes entre configurações."), PageBreak()]

    story += [P("3. Dados e benchmark", "H1x"), styled_table([["Item", "Quantidade/estado"], ["PDFs fornecidos manualmente", "18"], ["PDFs indexados", "18"], ["Chunks/vetores", "951"], ["Editais no benchmark", "10"], ["Desenvolvimento/teste", "7/3"], ["Referências humanas", "30/30 validadas"]], [8.0*cm, 7.5*cm]), P("Os 18 PDFs foram colocados manualmente pelo usuário. Eles não foram carregados pelo sistema e não recebem proveniência PNCP retroativa."), P("Campos críticos", "H2x")] + bullets(["Valor estimado.", "Modalidade.", "Prazo de entrega da proposta."]) + [P("Cada referência contém valor, página, trecho e identificação do revisor. A importação foi transacional e validou a presença literal da evidência no PDF."), P("4. Protocolo experimental", "H1x"), styled_table([["Parâmetro", "Valor"], ["Modelo", "openai/gpt-oss-120b via Groq free tier"], ["Temperatura / reasoning", "0 / low"], ["Máximo de saída", "800 tokens"], ["Chunks", "300, 500 e 800 palavras"], ["Overlaps", "50 e 80 palavras"], ["Top-k", "3 e 5"], ["Configurações RAG", "12"], ["Baselines", "Regex e LLM sem recuperação"], ["Linhas desenvolvimento/teste", "294 / 27"]], [6.0*cm, 9.5*cm]), P("O contexto do juiz RAGAS foi limitado a 12.000 caracteres, priorizando o chunk da evidência e os demais por similaridade. A medida foi necessária para o limite gratuito de 8.000 tokens por minuto e não alterou as respostas geradas."), PageBreak()]

    story += [P("5. Seleção no desenvolvimento", "H1x"), P(f"Configuração selecionada: <b>{selected['selected_config_id']}</b>. O arquivo registra <i>source_split: development</i> e foi congelado com SHA-256 antes do teste."), P("Critério hierárquico: Answer Correctness descendente, Faithfulness descendente, alucinação ascendente, custo ascendente e latência ascendente."), P("A configuração selecionada respondeu apenas 2/21 campos no desenvolvimento. Ambas as respostas tiveram métricas 1,00. A baixa cobertura (9,5%) deixa a escolha sensível ao pequeno n e deve ser tratada como limitação metodológica."), chart(FIGS / "configuracoes_desenvolvimento.png", 16.0*cm), PageBreak()]

    result_data = [["Abordagem", "Resp.", "Cobertura", "Faithfulness", "Correctness", "Alucinação"], ["Regex", "3/9", "33,3%", f"{regex['faithfulness']['mean']:.4f}", f"{regex['answer_correctness']['mean']:.4f}", f"{regex['hallucination_rate']:.1%}"], ["LLM sem RAG", "1/9", "11,1%", f"{llm['faithfulness']['mean']:.4f}", f"{llm['answer_correctness']['mean']:.4f}", f"{llm['hallucination_rate']:.1%}"], ["RAG selecionado", "2/9", "22,2%", f"{rag['faithfulness']['mean']:.4f}", f"{rag['answer_correctness']['mean']:.4f}", f"{rag['hallucination_rate']:.1%}"]]
    story += [P("6. Resultado final no teste", "H1x"), styled_table(result_data, [3.7*cm, 1.4*cm, 2.2*cm, 2.7*cm, 2.7*cm, 2.4*cm]), P("As métricas RAGAS são médias somente sobre campos respondidos: n=3 para regex, n=1 para LLM sem RAG e n=2 para o RAG selecionado."), chart(FIGS / "metricas_finais_teste.png", 15.8*cm), PageBreak(), P("Alucinação no teste", "H1x"), chart(FIGS / "alucinacao_final_teste.png", 15.8*cm), P("O RAG selecionado produziu uma resposta classificada como contraditória entre as duas respostas existentes, resultando em 50%."), P("7. Teste da hipótese", "H1x"), styled_table([["Meta", "Limiar", "Observado", "Resultado"], ["Faithfulness", ">= 0,85", "1,0000", "Atingida"], ["Answer Correctness", ">= 0,80", "0,8469", "Atingida"], ["Alucinação", "<= 10%", "50,0%", "Não atingida"]], [4.7*cm, 3.2*cm, 3.5*cm, 4.0*cm]), P("Conclusão: hipótese parcialmente confirmada.", "Callout"), PageBreak()]

    story += [P("8. Análise de erros", "H1x"), P(f"A análise classificou <b>{errors['counts'].get('campo_ausente_ou_nao_extraido', 0)}</b> casos de campo ausente/não extraído e <b>{errors['counts'].get('modalidade_incorreta', 0)}</b> diferenças de modalidade."), P("Erro dominante: cobertura", "H2x"), P("No RAG selecionado, sete dos nove campos permaneceram sem resposta. Melhorar a recuperação e a extração é mais importante do que otimizar pequenas diferenças entre médias condicionais."), P("Normalização de modalidade", "H2x"), P("A resposta RAG 'LEILÃO ELETRÔNICO, do tipo MAIOR LANCE' foi comparada à referência 'leilão eletrônico'. O conteúdo traz a modalidade correta e um qualificador adicional, mas foi tratado como contradição. A avaliação futura deve separar modalidade, meio eletrônico e critério/tipo."), P("Recomendações", "H2x")] + bullets(["Usar cobertura mínima como gate de seleção.", "Normalizar modalidade por componentes.", "Criar consultas específicas por campo e reforçar recuperação de prazos e valores.", "Ampliar o benchmark e reportar intervalos de confiança."])

    story += [PageBreak(), P("9. Custo e latência", "H1x"), styled_table([["Etapa", "Tokens de geração", "Custo teórico"], ["Desenvolvimento", "234.879", "US$ 0,04427730"], ["Teste", "10.517", "US$ 0,00219495"], ["Total", "245.396", "US$ 0,04647225"]], [6.0*cm, 5.0*cm, 4.5*cm]), P("O experimento utilizou o plano gratuito. Os valores são equivalentes às tarifas on-demand configuradas, não cobranças observadas. As chamadas internas do RAGAS não expõem uso consolidado e não estão incluídas."), KeepTogether([P("Custo médio por linha no teste", "H2x"), chart(FIGS / "custo_final_teste.png", 14.7*cm)]), PageBreak(), P("Latência média por linha no teste", "H1x"), chart(FIGS / "latencia_final_teste.png", 15.8*cm), P("A regex foi praticamente instantânea, enquanto a geração LLM levou em média 20,64 s e o RAG 24,54 s por linha. O custo adicional do RAG decorre do contexto recuperado."), PageBreak()]

    story += [P("10. PNCP/Compras.gov.br e proveniência", "H1x"), P("O objetivo de coleta oficial foi tratado com um conector opcional para a API pública do PNCP. O módulo consulta contratações por publicação, lista documentos e baixa PDFs específicos."), styled_table([["Controle", "Implementação"], ["Origem", "URL oficial e identificadores PNCP"], ["Integridade", "SHA-256"], ["Formato", "Assinatura %PDF-"], ["Tamanho", "Máximo de 50 MB"], ["Proveniência", "Data, título, tipo e publicação PNCP"], ["Isolamento", "Downloads não entram automaticamente no benchmark"]], [5.0*cm, 10.5*cm]), P("A consulta online de fumaça em 22/07/2026 expirou após as retentativas. A integração possui testes simulados, mas a coleta real deve ser repetida quando o endpoint estiver disponível. Não se afirma que os 18 PDFs existentes foram obtidos por API."), P("11. Reprodutibilidade", "H1x"), P("Ambiente adotado: Python global, conforme decisão do usuário. A suíte final possui 41 testes aprovados."), P("Comandos", "H2x"), P("python -m pytest -q tests<br/>python evaluation/run_experiments.py --benchmark evaluation/benchmark.json --split development<br/>python evaluation/run_experiments.py --benchmark evaluation/benchmark.json --split test<br/>python evaluation/generate_reports.py<br/>python scripts/collect_pncp.py search --start 20260701 --end 20260702 --modality 6 --page 1 --uf CE", "Smallx"), PageBreak()]

    story += [P("12. Limitações", "H1x")] + bullets(["Teste com 3 documentos e 9 campos.", "Cobertura RAG de 22,2% no teste.", "Seleção favoreceu escores condicionais calculados sobre somente duas respostas.", "Uso interno de tokens do RAGAS não consolidado.", "Contexto do juiz limitado a 12.000 caracteres no plano gratuito.", "Consulta real ao PNCP indisponível no teste online."]) + [P("13. Conclusão", "H1x"), P("O núcleo técnico, o benchmark humano e a avaliação final foram concluídos. O RAG apresentou alta fidelidade e correção média nas respostas existentes, mas não atingiu a meta de alucinação e respondeu poucos campos. O resultado não confirma integralmente a hipótese."), P("O próximo ciclo deve priorizar cobertura, normalização e tamanho de amostra. Depois dessas correções, o protocolo pode ser repetido mantendo o mesmo isolamento entre desenvolvimento e teste."), P("Status final: hipótese parcialmente confirmada; MVP funcional; evidência experimental concluída com limitações explícitas.", "Callout"), Spacer(1, 0.18 * cm), P("Referências e artefatos", "H2x")] + bullets(["API PNCP: https://pncp.gov.br/api/consulta/swagger-ui/index.html", "Manual PNCP: https://pncp.gov.br/manual/pt-br/latest/singlehtml/index.html", "RAGAS: https://docs.ragas.io/", "LlamaIndex: https://docs.llamaindex.ai/", "Resultados: evaluation/results/", "Gráficos: docs/figs/"])

    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    print(OUTPUT)


if __name__ == "__main__":
    build()
