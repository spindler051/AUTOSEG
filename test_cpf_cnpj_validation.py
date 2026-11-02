"""Testes locais de validação matemática de CPF/CNPJ (sem consulta externa)."""
import cadastros_v9 as cad


def test_cpf():
    assert cad.cpf_valido("52998224725")
    assert cad.cpf_valido("529.982.247-25")
    assert not cad.cpf_valido("11111111111")
    assert not cad.cpf_valido("12345678900")
    assert not cad.cpf_valido("52998224724")
    assert cad.validar_documento("Física", "529.982.247-25") == "52998224725"


def test_cnpj():
    assert cad.cnpj_valido("11222333000181")
    assert cad.cnpj_valido("11.222.333/0001-81")
    assert not cad.cnpj_valido("11111111111111")
    assert not cad.cnpj_valido("12345678901234")
    assert cad.validar_documento("Jurídica", "11.222.333/0001-81") == "11222333000181"


def test_mensagens():
    for tipo, documento, trecho in (
        ("Física", "123", "11 dígitos"),
        ("Física", "11111111111", "sequência"),
        ("Física", "12345678900", "verificadores"),
        ("Jurídica", "123", "14 dígitos"),
        ("Jurídica", "11111111111111", "sequência"),
        ("Jurídica", "12345678901234", "verificadores"),
    ):
        try:
            cad.validar_documento(tipo, documento)
        except ValueError as erro:
            assert trecho in str(erro), (documento, erro)
        else:
            raise AssertionError(f"aceitou documento inválido: {documento}")


def test_tamanho_automatico():
    assert cad.validar_documento_auto("52998224725") == "52998224725"
    assert cad.validar_documento_auto("11222333000181") == "11222333000181"
    assert cad.validar_documento_auto("") == ""
    try:
        cad.validar_documento_auto("123")
    except ValueError as erro:
        assert "11 dígitos" in str(erro)
    else:
        raise AssertionError("aceitou documento de tamanho inválido")


if __name__ == "__main__":
    test_cpf()
    test_cnpj()
    test_mensagens()
    test_tamanho_automatico()
    print("TESTES_CPF_CNPJ_OK")
