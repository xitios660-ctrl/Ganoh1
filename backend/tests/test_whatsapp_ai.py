import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "routers" / "whatsapp_ai.py"
spec = importlib.util.spec_from_file_location("ganoh_whatsapp_ai", MODULE_PATH)
whatsapp_ai = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(whatsapp_ai)

classify_intent = whatsapp_ai.classify_intent
extract_response_text = whatsapp_ai.extract_response_text
requests_mutation = whatsapp_ai.requests_mutation
parse_json_object = whatsapp_ai.parse_json_object


def test_classify_financial_intents():
    assert classify_intent("Quanto vendeu hoje?") == "sales"
    assert classify_intent("Quem está devendo?") == "debts"
    assert classify_intent("Quais pagamentos de prazo entraram?") == "prazo_payments"
    assert classify_intent("Tem estoque baixo?") == "stock"
    assert classify_intent("Me manda um resumo geral") == "summary"


def test_blocks_financial_mutation_requests():
    assert requests_mutation("Confirme esse PIX")
    assert requests_mutation("Zera a dívida do João")
    assert requests_mutation("Registra um saque no caixa")
    assert not requests_mutation("Quanto entrou em PIX?")
    assert not requests_mutation("Quem está devendo?")


def test_extract_response_text_from_raw_responses_payload():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Resposta segura."}
                ]
            }
        ]
    }
    assert extract_response_text(payload) == "Resposta segura."


def test_parse_json_object_from_model_fence():
    parsed = parse_json_object("""\`\`\`json
{"amount": 25.5, "payer_name": "Cliente", "confidence": 0.9}
\`\`\`""")
    assert parsed["amount"] == 25.5
    assert parsed["payer_name"] == "Cliente"


def test_parse_json_object_rejects_non_json():
    try:
        parse_json_object("não encontrei comprovante")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
