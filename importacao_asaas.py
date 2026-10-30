"""AUTOSEG 9.6 — Importação não destrutiva da base exportada do Asaas.

Fonte: database/clientes_asaas_preparados.db (SQLite independente).
Não importa senhas, contas de login, vínculos de síndico nem autorizações.
Uma transação única preserva cadastros preexistentes e OS. Reexecução idempotente.
"""
import argparse
import os
from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import closing

from banco import criar_banco
import prestadores_ext as ext
import cadastros_v9 as cad

CAMPOS = ('tipo_pessoa', 'documento', 'nome', 'nome_fantasia', 'endereco', 'numero',
          'complemento', 'bairro', 'cep', 'cidade', 'uf', 'telefone', 'email',
          'sindico_nome', 'sindico_telefone', 'sindico_email', 'administradora',
          'administradora_email', 'administradora_telefone', 'observacoes')


def _colunas(c,tabela):
    return {x['name'] for x in c.execute('PRAGMA table_info('+tabela+')')}


def _documento_doc(c,doc):
    # Cadastros antigos podem estar formatados (XX.XXX.XXX/XXXX-XX).
    for row in c.execute('SELECT id,documento,nome FROM clientes WHERE documento IS NOT NULL AND documento != ""'):
        if cad.digitos(row['documento'])==doc:
            return row
    return None


def _backup_sqlite(origem, caminho_backup):
    # API SQLite backup garante snapshot consistente inclusive com WAL ativo.
    caminho_backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(origem)) as origem_con:
        with sqlite3.connect(str(caminho_backup)) as backup_con:
            origem_con.backup(backup_con)
    os.chmod(caminho_backup, 0o600)


def importar(arquivo_fonte, destino, backup=True):
    """Importa clientes e organizações; não substitui registros existentes nem senhas.

    Retorna contagem para auditoria. Interrompe a operação em caso de fonte inválida.
    """
    arquivo_fonte=Path(arquivo_fonte).expanduser().resolve()
    destino=Path(destino).expanduser().resolve()
    if arquivo_fonte==destino:
        raise ValueError('A base do Asaas não pode ser o próprio banco de produção.')
    if not arquivo_fonte.is_file():
        raise FileNotFoundError('Base preparada não encontrada: '+str(arquivo_fonte))
    if destino.exists() and backup:
        arquivo_backup=destino.with_name('dados_antes_importacao_asaas_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        _backup_sqlite(destino,arquivo_backup)
    else:
        arquivo_backup=None
    criar_banco(str(destino))
    ext.instalar(str(destino))
    cad.instalar(str(destino))
    resumo={'novos_clientes':0,'existentes_preservados':0,'novas_organizacoes':0,
            'organizacoes_preservadas':0,'linhas_origem':0,'duplicidades_revisao':0,
            'backup':str(arquivo_backup) if arquivo_backup else ''}
    with closing(sqlite3.connect(str(arquivo_fonte))) as f:
        f.row_factory=sqlite3.Row
        ok=f.execute('PRAGMA quick_check').fetchone()[0]
        if ok!='ok':raise ValueError('Banco de origem inválido: '+str(ok))
        tabelas={x[0] for x in f.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'clientes','autoseg_asaas_origens'}.issubset(tabelas):
            raise ValueError('Banco preparado não contém a estrutura de importação do Asaas.')
        origem_clientes=f.execute('SELECT * FROM clientes ORDER BY id').fetchall()
        origem_linhas=f.execute('SELECT * FROM autoseg_asaas_origens ORDER BY linha_excel').fetchall()
        # Não confia em permissões de um banco de origem externo.
        if len(origem_clientes)>10000 or len(origem_linhas)>30000:
            raise ValueError('Base de importação excede limites esperados; revise o arquivo.')
    with ext.db(str(destino)) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''CREATE TABLE IF NOT EXISTS autoseg_asaas_origens (
            linha_excel INTEGER PRIMARY KEY, documento TEXT NOT NULL, nome_original TEXT NOT NULL,
            email_original TEXT DEFAULT '', emails_adicionais TEXT DEFAULT '',
            conflito_nome INTEGER NOT NULL DEFAULT 0, criado_em TEXT NOT NULL)''')
        cols=_colunas(c,'clientes')
        ins_cols=[col for col in CAMPOS if col in cols]
        for x in origem_clientes:
            doc=cad.digitos(x['documento'])
            if not (cad.cnpj_valido(doc) if len(doc)==14 else cad.cpf_valido(doc)):
                raise ValueError('Documento inválido na base importada; operação cancelada.')
            existente=_documento_doc(c,doc)
            if existente:
                cid=existente['id']
                # Não sobrescreve alterações feitas por usuários no banco de produção.
                resumo['existentes_preservados']+=1
                fields_atualizaveis=[col for col in ins_cols if col not in ('documento','nome','tipo_pessoa','observacoes')]
                for col in fields_atualizaveis:
                    if str(x[col] or '').strip():
                        c.execute(f'''UPDATE clientes SET {col}=? WHERE id=? AND TRIM(COALESCE({col},''))='' ''',
                                  (x[col],cid))
                # Apenas anexa indicação de importação se nenhuma observação existia.
                if x['observacoes']:
                    c.execute("UPDATE clientes SET observacoes=? WHERE id=? AND TRIM(COALESCE(observacoes,''))=''",(x['observacoes'],cid))
            else:
                p=','.join('?' for _ in ins_cols)
                cid=c.execute('INSERT INTO clientes('+','.join(ins_cols)+',status,criado_em) VALUES('+p+',?,?)',
                              [x[col] for col in ins_cols]+['Ativo',ext.agora()]).lastrowid
                resumo['novos_clientes']+=1
            if len(doc)==14:
                o=c.execute('SELECT id,cliente_id FROM v9_organizacoes WHERE cnpj=? AND mesclado_em IS NULL',(doc,)).fetchone()
                if o:
                    resumo['organizacoes_preservadas']+=1
                    if o['cliente_id'] is None:
                        c.execute('UPDATE v9_organizacoes SET cliente_id=? WHERE id=? AND cliente_id IS NULL',(cid,o['id']))
                else:
                    nome=x['nome']
                    tipo='Condomínio' if 'condom' in _sem_acentos(nome) or 'edificio' in _sem_acentos(nome) or 'residencial' in _sem_acentos(nome) else 'Empresa'
                    c.execute('''INSERT INTO v9_organizacoes(cliente_id,nome,tipo,cnpj,cidade,bairro,situacao,criado_em)
                                 VALUES(?,?,?,?,?,?,?,?)''',
                              (cid,nome,tipo,doc,x['cidade'] or '',x['bairro'] or '',
                               'Importado - revisar',ext.agora()))
                    resumo['novas_organizacoes']+=1
        for l in origem_linhas:
            c.execute('''INSERT OR IGNORE INTO autoseg_asaas_origens
                (linha_excel,documento,nome_original,email_original,emails_adicionais,conflito_nome,criado_em)
                VALUES(?,?,?,?,?,?,?)''',
                (l['linha_excel'],l['documento'],l['nome_original'],l['email_original'],
                 l['emails_adicionais'],l['conflito_nome'],l['criado_em']))
        resumo['linhas_origem']=c.execute('SELECT COUNT(*) FROM autoseg_asaas_origens').fetchone()[0]
        resumo['duplicidades_revisao']=c.execute('SELECT COUNT(DISTINCT documento) FROM autoseg_asaas_origens WHERE conflito_nome=1').fetchone()[0]
    os.chmod(destino,0o600)
    return resumo


def _sem_acentos(txt):
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFKD',str(txt).casefold()) if not unicodedata.combining(ch))


def main():
    ap=argparse.ArgumentParser(description='Importação idempotente Asaas -> AUTOSEG, sem importar senhas')
    ap.add_argument('--origem',required=True,help='SQLite preparado de clientes Asaas')
    ap.add_argument('--destino',required=True,help='dados.db do AUTOSEG (será preservado e atualizado)')
    args=ap.parse_args()
    r=importar(args.origem,args.destino,backup=True)
    print('Importação concluída. Novos clientes:',r['novos_clientes'],
          '| Cadastros existentes preservados:',r['existentes_preservados'],
          '| Novas organizações:',r['novas_organizacoes'],
          '| Organizações preservadas:',r['organizacoes_preservadas'],
          '| Linhas de origem:',r['linhas_origem'])
    print('Documentos repetidos para revisão:',r['duplicidades_revisao'])
    if r['backup']:print('Cópia anterior do banco:',r['backup'])
    print('Nenhuma senha, conta PF ou autorização de síndico foi criada.')

if __name__=='__main__':main()
