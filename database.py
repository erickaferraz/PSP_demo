import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

import psycopg2
import os

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT"),
        sslmode='require'  # <--- ESSENCIAL PARA O NEON
    )

def init_db():
    conn = None
    try:
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS municipios (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                cnpj VARCHAR(18) UNIQUE NOT NULL,
                saldo_atual NUMERIC(15,2) DEFAULT 0.00,
                criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cobrancas (
                id SERIAL PRIMARY KEY,
                municipio_id INTEGER REFERENCES municipios(id),
                tipo_tributo VARCHAR(50),
                valor_bruto NUMERIC(15,2) NOT NULL,
                taxa_psp NUMERIC(15,2) DEFAULT 0.00,
                status VARCHAR(20) DEFAULT 'pendente',
                metodo_pagamento VARCHAR(50) DEFAULT 'Pix',
                data_pagamento TIMESTAMP WITH TIME ZONE,
                criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        cur.close()
    except Exception as e:
        print(f"Erro: {e}")
    finally:
        if conn: conn.close()

def cadastrar_municipio(nome, cnpj):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO municipios (nome, cnpj) VALUES (%s, %s) ON CONFLICT (cnpj) DO NOTHING RETURNING id;", (nome, cnpj))
        res = cur.fetchone()
        conn.commit()
        return res[0] if res else None
    finally:
        cur.close(); conn.close()

def criar_cobranca(municipio_id, tributo, valor, metodo):
    conn = get_connection()
    cur = conn.cursor()
    try:
        m_id = int(municipio_id)
        cur.execute("""
            INSERT INTO cobrancas (municipio_id, tipo_tributo, valor_bruto, taxa_psp, metodo_pagamento)
            VALUES (%s, %s, %s, 0.90, %s) RETURNING id;
        """, (m_id, tributo, valor, metodo))
        id_c = cur.fetchone()[0]
        conn.commit()
        return id_c
    finally:
        cur.close(); conn.close()

def registrar_pagamento(cobranca_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        c_id = int(cobranca_id)
        cur.execute("SELECT municipio_id, valor_bruto FROM cobrancas WHERE id = %s AND status = 'pendente'", (c_id,))
        res = cur.fetchone()
        if res:
            mun_id, valor = res
            cur.execute("UPDATE cobrancas SET status = 'pago', data_pagamento = NOW() WHERE id = %s", (c_id,))
            cur.execute("UPDATE municipios SET saldo_atual = saldo_atual + %s WHERE id = %s", (valor, mun_id))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def registrar_saque(municipio_id, valor_saque):
    conn = get_connection()
    try:
        cur = conn.cursor()
        m_id = int(municipio_id)
        cur.execute("SELECT saldo_atual FROM municipios WHERE id = %s", (m_id,))
        saldo = cur.fetchone()[0]
        if saldo >= valor_saque:
            cur.execute("UPDATE municipios SET saldo_atual = saldo_atual - %s WHERE id = %s", (valor_saque, m_id))
            cur.execute("""
                INSERT INTO cobrancas (municipio_id, tipo_tributo, valor_bruto, status, metodo_pagamento, data_pagamento)
                VALUES (%s, 'SAQUE (Transferência)', %s, 'pago', 'TED/PIX', NOW())
            """, (m_id, -valor_saque))
            conn.commit()
            return True, "Saque realizado!"
        return False, "Saldo insuficiente."
    finally:
        conn.close()

def obter_resumo_auditoria(municipio_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        m_id = int(municipio_id)
        cur.execute("""
            SELECT COUNT(*), SUM(CASE WHEN status='pago' THEN 1 ELSE 0 END), 
            SUM(CASE WHEN status='pendente' THEN 1 ELSE 0 END),
            COALESCE(SUM(valor_bruto) FILTER (WHERE status='pago' AND valor_bruto > 0), 0)
            FROM cobrancas WHERE municipio_id = %s
        """, (m_id,))
        res = cur.fetchone()
        return tuple(0 if x is None else x for x in res)
    except:
        return (0, 0, 0, 0)
    finally:
        cur.close(); conn.close()