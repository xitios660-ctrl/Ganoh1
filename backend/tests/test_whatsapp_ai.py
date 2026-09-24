from routers.whatsapp_ai import classify_intent, extract_response_text, requests_mutation


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
