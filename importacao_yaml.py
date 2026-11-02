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
    if len(d)>3:
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
    if not 3<=len(resultado.get('nome',''))<=250:
        raise ValueError('Nome / Razão social deve ter pelo menos 3 caracteres.')
    tipo=resultado.setdefault('tipo_pessoa','Jurídica')
    if tipo not in ('Jurídica','Física'):
        raise ValueError('Tipo de pessoa inválido.')
    if resultado.setdefault('status','Ativo') not in ('Ativo','Inativo','Prospect'):
        raise ValueError('Status de cliente inválido.')
    doc=cad.digitos(resultado.get('documento',''))
    if doc and not (cad.cnpj_valido(doc) if tipo=='Jurídica' else cad.cpf_valido(doc)):
        raise ValueError('CPF/CNPJ inválido no arquivo.')
    return resultado


def relatorio(nome, conteudo, numero_os=None):
    """Modelo reutilizável: nunca identifica nem muda a OS aberta.

    'numero' é legado e ignorado, para compatibilidade com modelos antigos.
    Somente os campos presentes no YAML são preenchidos no formulário.
    """
    d=carregar(nome,conteudo)
    if set(d)-{'versao','os'} or not isinstance(d.get('os'), Mapping):
        raise ValueError('Utilize a seção os do modelo oficial.')
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
