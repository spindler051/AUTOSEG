"""Importação *somente para pré-preenchimento* no Portal do Prestador.

Nunca grava no SQLite: a tela normal exige revisão e confirmação humana.
"""
import re
from collections.abc import Mapping
from pathlib import Path

import cadastros_v9 as cad
import prestadores_ext as ext
from portal_negocios import CLIENTE_CAMPOS

LIMITE_BYTES = 64 * 1024
CAMPOS_RELATORIO = ('diagnostico', 'execucao', 'resultado', 'relatorio_tecnico')


def carregar(nome, conteudo):
    try:
        import yaml
        from yaml.events import AliasEvent
    except ImportError as exc:
        raise ValueError('Instale PyYAML: python -m pip install -r requirements.txt') from exc
    # The filename is informational. The content, size and UTF-8 validation
    # below are what matter; this avoids rejecting valid YAML renamed by the
    # user or exported without an extension.
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
    """Valida a lista `materiais` (financeiros) com mensagens específicas.

    - ``None`` é interpretado como lista vazia (sem lançamentos financeiros).
    - Valor não-lista gera erro específico.
    - Cada item deve ser um mapeamento com ``item``, ``quantidade`` e
      ``valor_unitario``; campos ausentes ou inválidos geram erro numerado.

    Nunca inventa quantidade, preço ou valor: campo ausente não vira zero e
    descrições em texto livre não viram lançamentos financeiros.
    """
    if materiais is None:
        return []
    if not isinstance(materiais, list):
        raise ValueError('O campo "materiais" deve ser uma lista.')
    if len(materiais) > 100:
        raise ValueError('Materiais deve ser uma lista de até 100 itens.')
    resposta = []
    for indice, material in enumerate(materiais, start=1):
        if not isinstance(material, Mapping):
            raise ValueError(f'Material {indice}: deve ser um item com os campos '
                             '"item", "quantidade" e "valor_unitario".')
        if material.get('item') is None or not str(material.get('item', '')).strip():
            raise ValueError(f'Material {indice}: campo "item" não informado.')
        item = str(material['item']).strip()
        if len(item) > 180:
            raise ValueError(f'Material {indice}: campo "item" excede 180 caracteres.')
        unidade = str(material.get('unidade', 'un') or 'un').strip()
        if len(unidade) > 40:
            raise ValueError(
                f'Material {indice}: campo "unidade" excede 40 caracteres.')
        if 'quantidade' not in material or material.get('quantidade') in (None, ''):
            raise ValueError(
                f'Material {indice}: campo "quantidade" não informado.'
                + (f' Item: "{item[:60]}".' if item else '')
                + ' Informe a quantidade usada ou remova este item da lista.')
        if 'valor_unitario' not in material or material.get('valor_unitario') in (None, ''):
            raise ValueError(
                f'Material {indice}: campo "valor_unitario" não informado.'
                + (f' Item: "{item[:60]}".' if item else '')
                + ' Informe o valor unitário ou remova este item da lista.')
        try:
            quantidade = _numero_decimal(material.get('quantidade'), 'Quantidade', False)
        except ValueError:
            raise ValueError(f'Material {indice}: campo "quantidade" inválido. Use número maior que zero.')
        try:
            valor = _numero_decimal(material.get('valor_unitario'), 'Valor unitário', True)
        except ValueError:
            raise ValueError(f'Material {indice}: campo "valor_unitario" inválido. Use número maior ou igual a zero.')
        resposta.append({
            'item': item,
            'quantidade': float(quantidade),
            'unidade': unidade,
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
    pagamento = str(entrada.get('forma_pagamento', '')).strip()
    if pagamento and pagamento not in ('PIX', 'Transferência', 'Dinheiro', 'Cartão', 'Boleto', 'Outro'):
        raise ValueError('Forma de pagamento inválida. Escolha PIX, Transferência, Dinheiro, Cartão, Boleto ou Outro.')
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


def _composicao_os(blocos, nivel='Componente'):
    """Valida a composição declarativa (pai + filhos) vinda do YAML da OS."""
    if blocos is None:
        return []
    if not isinstance(blocos, list):
        raise ValueError('O campo "composicao" deve ser uma lista.')
    if len(blocos) > 50:
        raise ValueError('Composição com componentes demais.')
    saida = []
    for indice, entrada in enumerate(blocos, start=1):
        if not isinstance(entrada, Mapping):
            raise ValueError(f'{nivel} {indice}: item inválido.')
        cid = str(entrada.get('id') or '').strip()
        if not cid:
            raise ValueError(f'{nivel} {indice}: informe o "id" do componente.')
        item = {'id': cid}
        if entrada.get('valor') not in (None, ''):
            item['valor'] = entrada['valor']
        if entrada.get('percentual') not in (None, ''):
            item['percentual'] = entrada['percentual']
        if entrada.get('residual'):
            item['residual'] = True
        if entrada.get('filhos') is not None:
            item['filhos'] = _composicao_os(entrada['filhos'], f'Filho {indice}')
        if ('valor' not in item and 'percentual' not in item
                and not item.get('residual') and not item.get('filhos')):
            raise ValueError(
                f'{nivel} {indice} ({cid}): informe valor, percentual ou residual.')
        saida.append(item)
    return saida


def relatorio(nome, conteudo, numero_os=None):
    """Modelo reutilizável: nunca identifica nem muda a OS aberta.

    Aceita tanto a saída limpa (``versao`` + ``os``) quanto o modelo oficial
    completo com instruções, exemplo e a seção ``modelo.os`` preenchida.
    """
    d=carregar(nome,conteudo)
    if 'modelo' in d and 'os' not in d:
        if set(d)-{'versao','instrucoes','modelo','exemplo'}:
            raise ValueError('O modelo oficial contém seções desconhecidas.')
        if not isinstance(d.get('modelo'), Mapping) or not isinstance(d['modelo'].get('os'), Mapping):
            raise ValueError('O modelo oficial deve conter modelo.os.')
        entrada=d['modelo'].get('os') or {}
    else:
        if set(d)-{'versao','os'} or not isinstance(d.get('os'), Mapping):
            raise ValueError('Utilize a seção os do modelo oficial. A saída não deve conter instruções nem exemplo.')
        entrada=d['os']
    if not entrada:
        return {}
    if not any(str(entrada.get(k, '')).strip() for k in CAMPOS_RELATORIO) \
            and not entrada.get('materiais'):
        return {}
    if set(entrada)-{'numero','cliente','cliente_id','descricao','tecnico','forma_pagamento','urgencia','valor_mao_obra','valor_materiais','valor_materiais_manual','valor_total','valor_total_override','observacoes','diagnostico','execucao','resultado','relatorio_tecnico','materiais','composicao'}:
        raise ValueError('Campo de OS desconhecido no YAML.')
    resultado={}
    for k in CAMPOS_RELATORIO:
        if k not in entrada:continue
        v=entrada[k]
        if not isinstance(v,str) or len(v)>5000:
            raise ValueError(k+' deve ser texto de até 5.000 caracteres.')
        resultado['v9_'+k if k!='relatorio_tecnico' else k]=v.strip()
    if 'materiais' in entrada:
        resultado['material_yaml'] = [
            {'item': m['item'], 'quantidade': m['quantidade'],
             'valor_unitario': m['valor_unitario']}
            for m in _materiais_os_lista(entrada['materiais'])
        ]
    if 'composicao' in entrada:
        resultado['composicao_yaml'] = _composicao_os(entrada['composicao'])
    return resultado


def relatorio_os_yaml(banco, os_id):
    """Exporta o modelo completo, com instruções e dados atuais da OS."""
    import yaml
    with ext.db(banco) as c:
        o=c.execute('''SELECT o.numero_os,o.cliente_id,o.descricao,o.tecnico,
                             o.forma_pagamento,o.urgencia,o.valor_mao_obra,
                             o.valor_materiais,o.valor_total,o.observacoes,
                             c.nome cliente
                      FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id
                      WHERE o.id=?''',(os_id,)).fetchone()
        if not o:
            raise ValueError('OS não encontrada.')
        detalhes=None
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v9_detalhes_os'").fetchone():
            detalhes=c.execute('SELECT diagnostico,execucao,resultado FROM v9_detalhes_os WHERE os_id=?',
                               (os_id,)).fetchone()
        andamento=None
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='os_atendimentos'").fetchone():
            andamento=c.execute('SELECT rascunho FROM os_atendimentos WHERE os_id=?',
                                (os_id,)).fetchone()
        encerramento=None
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='os_encerramentos'").fetchone():
            encerramento=c.execute('SELECT relatorio FROM os_encerramentos WHERE os_id=?',
                                   (os_id,)).fetchone()
        materiais=c.execute('SELECT item,quantidade,unidade,valor_unitario FROM materiais_os '
                            'WHERE os_id=? ORDER BY id',(os_id,)).fetchall()
    dados={'numero':str(o['numero_os'] or ''),
           'cliente_id':int(o['cliente_id']),
           'cliente':str(o['cliente'] or ''),
           'descricao':str(o['descricao'] or ''),
           'tecnico':str(o['tecnico'] or ''),
           'forma_pagamento':str(o['forma_pagamento'] or ''),
           'urgencia':str(o['urgencia'] or ''),
           'valor_mao_obra':float(o['valor_mao_obra'] or 0),
           'valor_materiais':float(o['valor_materiais'] or 0),
           'valor_total':float(o['valor_total'] or 0),
           'observacoes':str(o['observacoes'] or '')}
    for chave,coluna in (('diagnostico','diagnostico'),('execucao','execucao'),('resultado','resultado')):
        valor=(detalhes[coluna] if detalhes else '') or ''
        dados[chave]=str(valor).strip()
    relato=((encerramento['relatorio'] if encerramento else '') or
            (andamento['rascunho'] if andamento else '') or '')
    dados['relatorio_tecnico']=str(relato).strip()
    itens=[]
    for m in materiais:
        if m['quantidade'] is None:
            continue
        item={'item':m['item'],'quantidade':float(m['quantidade']),
              'valor_unitario':float(m['valor_unitario'] or 0)}
        if str(m['unidade'] or '').strip():
            item['unidade']=str(m['unidade']).strip()
        itens.append(item)
    dados['materiais']=itens
    modelo_path=Path(__file__).with_name('modelo_relatorio_os.yaml')
    config=yaml.safe_load(modelo_path.read_text(encoding='utf-8'))
    config.setdefault('modelo',{})
    config['modelo']['os']=dados
    return yaml.safe_dump(config,allow_unicode=True,sort_keys=False)


def _texto_orcamento(entrada, chave, limite):
    valor = entrada.get(chave, '')
    if valor is None:
        return ''
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        raise ValueError(f'Campo "{chave}" deve ser texto simples.')
    texto = str(valor).strip()
    if len(texto) > limite:
        raise ValueError(f'Campo "{chave}" excede {limite} caracteres.')
    return texto


def _cliente_orcamento(banco, entrada):
    identificadores = {
        'cliente_id': _texto_orcamento(entrada, 'cliente_id', 30),
        'cliente_documento': _texto_orcamento(entrada, 'cliente_documento', 30),
        'cliente_nome': _texto_orcamento(entrada, 'cliente_nome', 250),
    }
    preenchidos = [chave for chave, valor in identificadores.items() if valor]
    if len(preenchidos) != 1:
        raise ValueError('Informe exatamente um cliente: cliente_id, cliente_documento ou cliente_nome. Deixe os outros vazios.')
    with ext.db(banco) as c:
        if identificadores['cliente_id']:
            try:
                cliente_id = int(identificadores['cliente_id'])
            except (TypeError, ValueError) as exc:
                raise ValueError('cliente_id deve ser um número inteiro positivo.') from exc
            if cliente_id <= 0:
                raise ValueError('cliente_id deve ser um número inteiro positivo.')
            cliente = c.execute(
                "SELECT id,nome,documento FROM clientes WHERE id=? AND status!='Inativo'",
                (cliente_id,)).fetchone()
            if not cliente:
                raise ValueError(f'Cliente {cliente_id} não encontrado ou inativo.')
            return dict(cliente)

        candidatos = [dict(x) for x in c.execute(
            "SELECT id,nome,documento FROM clientes WHERE status!='Inativo'")]
        if identificadores['cliente_documento']:
            documento = cad.digitos(identificadores['cliente_documento'])
            if len(documento) not in (11, 14):
                raise ValueError('CPF/CNPJ do cliente deve ter 11 ou 14 dígitos.')
            encontrados = [x for x in candidatos if cad.digitos(x['documento']) == documento]
            referencia = documento
        else:
            nome = identificadores['cliente_nome'].casefold()
            encontrados = [x for x in candidatos if (x['nome'] or '').strip().casefold() == nome]
            referencia = identificadores['cliente_nome']
        if not encontrados:
            raise ValueError(f'Cliente não encontrado ou inativo: {referencia[:120]}')
        if len(encontrados) > 1:
            raise ValueError('Há mais de um cliente ativo com essa identificação. Use cliente_id ou cliente_documento.')
        return encontrados[0]


def orcamento(nome, conteudo, banco):
    """Valida YAML de orçamento e resolve cliente, serviços e materiais ativos.

    Assim como o modelo de relatório, o arquivo enviado deve conter apenas
    ``versao`` e ``orcamento``. O modelo oficial serve de rascunho e inclui as
    instruções que devem ser removidas antes do envio. Nada é gravado.
    """
    import catalogo_servicos as cat

    d = carregar(nome, conteudo)
    if 'orcamento' in d:
        if set(d) - {'versao', 'orcamento'} or not isinstance(d.get('orcamento'), Mapping):
            raise ValueError('A saída deve conter apenas versao e a seção orcamento.')
        entrada = d['orcamento']
    elif 'modelo' in d:
        if set(d) - {'versao', 'instrucoes', 'modelo', 'exemplo'}:
            raise ValueError('O modelo oficial contém seções desconhecidas.')
        modelo = d.get('modelo')
        if not isinstance(modelo, Mapping) or not isinstance(modelo.get('orcamento'), Mapping):
            raise ValueError('O modelo oficial deve conter modelo.orcamento.')
        # Modelo em branco: nada a importar até a pessoa gerar a saída limpa
        # com versao + orcamento, como no modelo de relatório técnico.
        return {}
    else:
        raise ValueError('Utilize a seção orcamento do modelo oficial.')

    aceitos = {'cliente_id', 'cliente_documento', 'cliente_nome', 'servicos', 'materiais'}
    if set(entrada) - aceitos:
        raise ValueError('Campo desconhecido no orçamento: '
                         + str(next(iter(set(entrada) - aceitos))))
    cliente = _cliente_orcamento(banco, entrada)
    servicos = entrada.get('servicos', [])
    materiais = entrada.get('materiais', [])
    if not isinstance(servicos, list):
        raise ValueError('O campo "servicos" deve ser uma lista.')
    if not isinstance(materiais, list):
        raise ValueError('O campo "materiais" deve ser uma lista.')
    resultado = cat.montar_itens_orcamento(banco, servicos, materiais)
    return {
        'cliente_id': cliente['id'],
        'cliente_nome': cliente['nome'],
        'servicos': [{'id': x['id'], 'quantidade': x['quantidade']}
                     for x in resultado['servicos']],
        'materiais': [{'id': x['id'], 'quantidade': str(x['quantidade'])}
                      for x in resultado['materiais']],
        'total_centavos': resultado['total_centavos'],
    }


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
  forma_pagamento: ""
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
    unidade: un
    valor_unitario: 0
"""
