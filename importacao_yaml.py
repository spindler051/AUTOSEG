"""Importação *somente para pré-preenchimento* no Portal do Prestador.

Nunca grava no SQLite: a tela normal exige revisão e confirmação humana.
"""
import re
from collections.abc import Mapping

import cadastros_v9 as cad
from portal_negocios import CLIENTE_CAMPOS

LIMITE_BYTES = 64 * 1024
CAMPOS_RELATORIO = ('diagnostico', 'execucao', 'resultado', 'relatorio_tecnico')


def carregar(nome, conteudo):
    try:
        import yaml
        from yaml.events import AliasEvent
    except ImportError as exc:
        raise ValueError('Instale PyYAML: python -m pip install -r requirements.txt') from exc
    if not str(nome).lower().endswith(('.yaml', '.yml')):
        raise ValueError('Envie um arquivo .yaml ou .yml.')
    if not isinstance(conteudo, bytes) or not 1 <= len(conteudo) <= LIMITE_BYTES:
        raise ValueError('Arquivo YAML vazio ou maior que 64 KB.')
    try:
        texto = conteudo.decode('utf-8-sig')
        # Sem aliases/âncoras: evita expansão recursiva de YAML.
        for evento in yaml.parse(texto, Loader=yaml.SafeLoader):
            if isinstance(evento, AliasEvent) or getattr(evento, 'anchor', None):
                raise ValueError('Aliases e âncoras YAML não são permitidos.')
        d = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ValueError('YAML inválido: revise a indentação e a estrutura.') from exc
    except UnicodeError as exc:
        raise ValueError('O YAML deve utilizar UTF-8.') from exc
    if not isinstance(d, Mapping) or d.get('versao') != 1:
        raise ValueError('Informe versao: 1 no início do arquivo.')
    if len(d)>4:
        raise ValueError('Estrutura YAML inesperada. Utilize o modelo oficial.')
    return d


def cliente(nome, conteudo):
    d=carregar(nome,conteudo)
    if set(d)-{'versao','cliente'} or not isinstance(d.get('cliente'), Mapping):
        raise ValueError('Utilize a seção cliente do modelo oficial.')
    entrada=d['cliente']
    if set(entrada)-set(CLIENTE_CAMPOS):
        raise ValueError('Campo de cliente desconhecido: '+str(next(iter(set(entrada)-set(CLIENTE_CAMPOS)))))
    resultado={}
    for k,v in entrada.items():
        if not isinstance(v, (str,int,float)) or isinstance(v,bool):
            raise ValueError('O campo '+k+' precisa ser texto simples.')
        valor=str(v).strip()
        if len(valor)>(2500 if k=='observacoes' else 250):
            raise ValueError('Campo '+k+' excede o limite.')
        resultado[k]=valor
    if len(resultado.get('nome',''))>250:
        raise ValueError('Nome / Razão social excede 250 caracteres.')
    tipo=resultado.setdefault('tipo_pessoa','Jurídica')
    if tipo not in ('Jurídica','Física'):
        raise ValueError('Tipo de pessoa inválido.')
    if resultado.setdefault('status','Ativo') not in ('Ativo','Inativo','Prospect'):
        raise ValueError('Status de cliente inválido.')
    doc=cad.digitos(resultado.get('documento',''))
    if doc and not (cad.cnpj_valido(doc) if tipo=='Jurídica' else cad.cpf_valido(doc)):
        raise ValueError('CPF/CNPJ inválido no arquivo.')
    return resultado


def _numero_decimal(valor, rotulo, permitir_zero=True):
    from decimal import Decimal, InvalidOperation
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        raise ValueError(rotulo + ' inválido.')
    try:
        n = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(rotulo + ' inválido.') from exc
    if not n.is_finite() or n < 0 or (n == 0 and not permitir_zero) or n > Decimal('1000000'):
        raise ValueError(rotulo + ' fora do intervalo permitido.')
    return n


def _materiais_os_lista(materiais):
    if not isinstance(materiais, list) or len(materiais) > 100:
        raise ValueError('Materiais deve ser uma lista de até 100 itens.')
    resposta = []
    for material in materiais:
        if (not isinstance(material, Mapping)
                or set(material) - {'item', 'quantidade', 'valor_unitario'}):
            raise ValueError('Material inválido: informe item, quantidade e valor_unitario.')
        item = str(material.get('item', '')).strip()
        if not 1 <= len(item) <= 180:
            raise ValueError('Informe o nome do material.')
        quantidade = _numero_decimal(material.get('quantidade', 1), 'Quantidade', False)
        valor = _numero_decimal(material.get('valor_unitario', 0), 'Valor unitário')
        resposta.append({
            'item': item,
            'quantidade': float(quantidade),
            'valor_unitario': float(valor),
            'valor_total': float(quantidade * valor),
        })
    return resposta


def materiais_os(nome, conteudo):
    """Valida uma lista de materiais para pré-preencher uma OS."""
    d = carregar(nome, conteudo)
    if set(d) != {'versao', 'materiais'}:
        raise ValueError('Utilize versao: 1 e a lista materiais do modelo oficial.')
    return _materiais_os_lista(d.get('materiais'))


def ordem_servico(nome, conteudo):
    """Valida uma OS para pré-preencher o formulário, sem gravar no banco."""
    d = carregar(nome, conteudo)
    if set(d) - {'versao', 'ordem_servico'} or not isinstance(d.get('ordem_servico'), Mapping):
        raise ValueError('Utilize a seção ordem_servico do modelo oficial.')
    entrada = d['ordem_servico']
    aceitos = {'cliente_id', 'cliente_documento', 'tecnico', 'descricao',
               'forma_pagamento', 'mao_obra', 'observacoes', 'urgencia', 'materiais'}
    if set(entrada) - aceitos:
        raise ValueError('Campo desconhecido na ordem de serviço: '
                         + str(next(iter(set(entrada) - aceitos))))
    descricao = str(entrada.get('descricao', '')).strip()
    if not 3 <= len(descricao) <= 2000:
        raise ValueError('Descrição da OS deve ter entre 3 e 2.000 caracteres.')
    cliente_id = entrada.get('cliente_id')
    documento = cad.digitos(entrada.get('cliente_documento', ''))
    if cliente_id is not None:
        try:
            cliente_id = int(cliente_id)
            if cliente_id <= 0:
                raise ValueError()
        except (TypeError, ValueError) as exc:
            raise ValueError('cliente_id deve ser um número positivo.') from exc
    if cliente_id is None and not documento:
        raise ValueError('Informe cliente_id ou cliente_documento.')
    pagamento = str(entrada.get('forma_pagamento', 'PIX')).strip() or 'PIX'
    if pagamento not in ('PIX', 'Transferência', 'Dinheiro', 'Cartão', 'Boleto', 'Outro'):
        raise ValueError('Forma de pagamento inválida.')
    urgencia = str(entrada.get('urgencia', 'Normal')).strip() or 'Normal'
    if urgencia not in ('Baixa', 'Normal', 'Alta'):
        raise ValueError('Urgência inválida.')
    return {
        'cliente_id': cliente_id,
        'cliente_documento': documento,
        'tecnico': str(entrada.get('tecnico', '')).strip()[:250],
        'descricao': descricao,
        'forma_pagamento': pagamento,
        'mao_obra': float(_numero_decimal(entrada.get('mao_obra', 0), 'Mão de obra')),
        'observacoes': str(entrada.get('observacoes', '')).strip()[:2500],
        'urgencia': urgencia,
        'materiais': _materiais_os_lista(entrada.get('materiais', [])),
    }


def relatorio(nome, conteudo, numero_os=None):
    """Modelo reutilizável: nunca identifica nem muda a OS aberta.

    'numero' é legado e ignorado, para compatibilidade com modelos antigos.
    Somente os campos presentes no YAML são preenchidos no formulário.
    """
    d=carregar(nome,conteudo)
    # Modelo oficial REV12: instrucoes + modelo.os + exemplo.
    # A saída preenchida deve trazer apenas versao e os.
    if 'modelo' in d and 'os' not in d:
        if set(d)-{'versao','instrucoes','modelo','exemplo'}:
            raise ValueError('O modelo oficial contém seções desconhecidas.')
        if not isinstance(d.get('modelo'), Mapping) or not isinstance(d['modelo'].get('os'), Mapping):
            raise ValueError('O modelo oficial deve conter modelo.os.')
        # Modelo em branco: nada a importar até o técnico/IA preencher a seção os.
        return {}
    if set(d)-{'versao','os'} or not isinstance(d.get('os'), Mapping):
        raise ValueError('Utilize a seção os do modelo oficial. A saída não deve conter instruções nem exemplo.')
    entrada=d['os']
    if set(entrada)-{'numero','diagnostico','execucao','resultado','relatorio_tecnico','materiais'}:
        raise ValueError('Campo de OS desconhecido no YAML.')
    resultado={}
    for k in CAMPOS_RELATORIO:
        if k not in entrada:continue
        v=entrada[k]
        if not isinstance(v,str) or len(v)>5000:
            raise ValueError(k+' deve ser texto de até 5.000 caracteres.')
        resultado['v9_'+k if k!='relatorio_tecnico' else k]=v.strip()
    if 'materiais' in entrada:
        materiais=entrada['materiais']
        if not isinstance(materiais,list) or len(materiais)>100:
            raise ValueError('Materiais deve ser uma lista de até 100 itens.')
        resultado['material_yaml']=[]
        for m in materiais:
            if not isinstance(m,Mapping) or set(m)-{'item','quantidade','valor_unitario'}:
                raise ValueError('Material inválido: informe item, quantidade e valor_unitario.')
            if not isinstance(m.get('item'),str) or not m['item'].strip():
                raise ValueError('Informe o nome do material.')
            try:
                from portal_negocios import numero
                q=numero(m.get('quantidade',1),'Quantidade')
                u=numero(m.get('valor_unitario',0),'Valor unitário')
            except (ValueError,TypeError) as exc:
                raise ValueError('Quantidade ou valor unitário inválido no material.') from exc
            if not q:raise ValueError('Quantidade deve ser positiva.')
            resultado['material_yaml'].append({'item':m['item'].strip()[:180], 'quantidade':q,'valor_unitario':u})
    return resultado


def servico(nome,conteudo):
    """Valida catálogo YAML para PRÉ-VISUALIZAÇÃO, sem gravação."""
    import catalogo_servicos as cat
    d=carregar(nome,conteudo)
    if set(d)-{'versao','servico'} or not isinstance(d.get('servico'),Mapping):
        raise ValueError('Utilize a seção servico do modelo oficial.')
    o=d['servico']
    if set(o)-{'nome','descricao','preco_servico','relatorio_padrao','materiais'}:
        raise ValueError('Campo não reconhecido no YAML de serviços.')
    out={}
    for k,lim in [('nome',140),('descricao',1500),('relatorio_padrao',5000)]:
        val=o.get(k,'')
        if not isinstance(val,str) or len(val)>lim:
            raise ValueError(f'{k} deve ser texto de até {lim} caracteres.')
        out[k]=val.strip()
    if not 3<=len(out['nome'])<=140:
        raise ValueError('Nome do serviço deve ter entre 3 e 140 caracteres.')
    preco=o.get('preco_servico',0)
    if isinstance(preco,bool) or not isinstance(preco,(str,int,float)):
        raise ValueError('Preço de mão de obra inválido.')
    cat._centavos(preco,'Preço do serviço')
    out['preco_servico']=str(preco)
    materiais=o.get('materiais',[])
    if not isinstance(materiais,list) or len(materiais)>30:
        raise ValueError('Máximo de 30 materiais por serviço.')
    linhas=[]
    for m in materiais:
        if not isinstance(m,Mapping) or set(m)-{'nome','quantidade','valor_unitario'}:
            raise ValueError('Cada material exige nome, quantidade e valor_unitario.')
        material=str(m.get('nome','')).strip()
        if not 1<=len(material)<=160:raise ValueError('Nome do material inválido.')
        qtd=m.get('quantidade',1)
        if isinstance(qtd,bool) or not isinstance(qtd,(str,int,float)):
            raise ValueError('Quantidade de material inválida.')
        try:
            from decimal import Decimal
            v=Decimal(str(qtd).replace(',','.'))
            if not v.is_finite() or v<=0 or v>1000:raise ValueError()
        except Exception:raise ValueError('Quantidade de material inválida.')
        preco_unit=m.get('valor_unitario',0)
        if isinstance(preco_unit,bool) or not isinstance(preco_unit,(str,int,float)):
            raise ValueError('Valor unitário inválido.')
        cat._centavos(preco_unit,'Material')
        linhas.append({'nome':material,'quantidade':str(qtd),'valor_unitario':str(preco_unit)})
    out['materiais_lista']=linhas
    return out


def materiais(nome, conteudo):
    """Valida lote para pré-visualização, sem criar registros automaticamente."""
    d=carregar(nome,conteudo)
    if set(d)-{'versao','materiais'} or not isinstance(d.get('materiais'),list):
        raise ValueError('Utilize versao: 1 e a lista materiais do modelo oficial.')
    linhas=d['materiais']
    if not 1<=len(linhas)<=100:
        raise ValueError('Informe entre 1 e 100 materiais.')
    aceitos={'nome','sku','unidade','custo','venda','minimo'}
    nomes=set()
    resposta=[]
    for m in linhas:
        if not isinstance(m,Mapping) or set(m)-aceitos:
            raise ValueError('Campos inválidos na lista de materiais.')
        nome_prod=str(m.get('nome','')).strip()
        if not 2<=len(nome_prod)<=160 or nome_prod.casefold() in nomes:
            raise ValueError('Nome inválido ou duplicado na lista: '+nome_prod[:60])
        nomes.add(nome_prod.casefold())
        data={'nome':nome_prod}
        for k,padrao in [('sku',''),('unidade','un'),('custo','0'),('venda','0'),('minimo','0')]:
            v=m.get(k,padrao)
            if isinstance(v,bool) or not isinstance(v,(str,int,float)):
                raise ValueError('Campo '+k+' do material precisa ser texto ou número.')
            data[k]=str(v).strip()
        if len(data['sku'])>50 or len(data['unidade'])>15:
            raise ValueError('SKU/unidade excedem o limite.')
        from estoque_materiais import _q,_valor_centavos
        if _q(data['minimo'],permitir_negativo=True)<0:
            raise ValueError('Estoque mínimo não pode ser negativo.')
        _valor_centavos(data['custo']);_valor_centavos(data['venda'])
        resposta.append(data)
    return resposta


MODELO_CLIENTE_VAZIO = """# Modelo vazio de cliente — preencha e importe no AUTOSEG.
versao: 1
cliente:
  tipo_pessoa: Jurídica
  nome: ""
  documento: ""
  endereco: ""
  numero: ""
  complemento: ""
  bairro: ""
  cep: ""
  cidade: ""
  uf: ""
  telefone: ""
  email: ""
  status: Prospect
  observacoes: ""
"""

MODELO_OS_VAZIO = """# Modelo vazio de ordem de serviço — preencha e importe no AUTOSEG.
# Informe cliente_id ou cliente_documento.
versao: 1
ordem_servico:
  cliente_id:
  cliente_documento: ""
  tecnico: ""
  descricao: ""
  forma_pagamento: PIX
  mao_obra: 0
  observacoes: ""
  urgencia: Normal
  materiais: []
"""

MODELO_MATERIAIS_VAZIO = """# Modelo vazio de materiais de estoque.
versao: 1
materiais:
  - nome: ""
    sku: ""
    unidade: un
    custo: "0"
    venda: "0"
    minimo: 0
"""

MODELO_MATERIAIS_OS_VAZIO = """# Modelo vazio de materiais para uma OS.
versao: 1
materiais:
  - item: ""
    quantidade: 1
    valor_unitario: 0
"""
