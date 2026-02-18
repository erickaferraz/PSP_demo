import streamlit as st
import pandas as pd
import plotly.express as px
import os
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fpdf import FPDF
from database import *

load_dotenv()
init_db()

st.set_page_config(page_title="Assat PSP - Gestão Pro", page_icon="🛡️", layout="wide")

st.markdown("<style>.stMetric {background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0;}</style>", unsafe_allow_html=True)

# --- PDF GENERATOR ---
def gerar_pdf_oficial(nome_mun, df_pagos, resumo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, f"Relatorio de Arrecadacao - {nome_mun}", ln=True, align='C')
    pdf.set_font("Arial", "", 10)
    pdf.cell(190, 10, f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 10, "Resumo Financeiro", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(190, 7, f"Total de Guias: {resumo[0]}", ln=True)
    pdf.cell(190, 7, f"Total Pago: R$ {float(resumo[3]):,.2f}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(40, 8, "Data", 1); pdf.cell(70, 8, "Tributo", 1); pdf.cell(40, 8, "Metodo", 1); pdf.cell(40, 8, "Valor", 1, ln=True)
    pdf.set_font("Arial", "", 9)
    for _, row in df_pagos.iterrows():
        pdf.cell(40, 7, str(row['data_pagamento'])[:10], 1)
        pdf.cell(70, 7, str(row['tipo_tributo']), 1)
        pdf.cell(40, 7, str(row['metodo_pagamento']), 1)
        pdf.cell(40, 7, f"R$ {row['valor_bruto']:,.2f}", 1, ln=True)
    return pdf.output(dest='S').encode('latin-1')

# --- LOGIN ---
if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if not st.session_state["autenticado"]:
    st.title("🏛️ Assat PSP - Acesso Restrito")
    with st.form("login"):
        u, s = st.text_input("Usuário"), st.text_input("Senha", type="password")
        if st.form_submit_button("Acessar"):
            if u == "admin" and s == "assat2026":
                st.session_state["autenticado"] = True
                st.rerun()
            else: st.error("Incorreto")
    st.stop()

# --- SIDEBAR ---
if st.sidebar.button("Logoff"): 
    st.session_state["autenticado"] = False
    st.rerun()

conn = get_connection()
df_mun = pd.read_sql("SELECT id, nome FROM municipios", conn)
conn.close()

if df_mun.empty:
    st.warning("Cadastre um município.")
    nome_n = st.sidebar.text_input("Nome")
    cnpj_n = st.sidebar.text_input("CNPJ")
    if st.sidebar.button("Salvar"):
        cadastrar_municipio(nome_n, cnpj_n); st.rerun()
    st.stop()

option = st.sidebar.selectbox('Município Ativo:', df_mun['nome'].tolist())
mun_id = int(df_mun[df_mun['nome'] == option]['id'].values[0])

# --- DADOS ---
conn = get_connection()
df_master = pd.read_sql(f"SELECT * FROM cobrancas WHERE municipio_id = {mun_id}", conn)
cur = conn.cursor(); cur.execute("SELECT saldo_atual FROM municipios WHERE id=%s", (mun_id,)); 
saldo_res = cur.fetchone()
saldo_at = float(saldo_res[0]) if saldo_res else 0.0
cur.close(); conn.close()
df_master['valor_bruto'] = df_master['valor_bruto'].astype(float)

# --- ALERTAS ---
st.subheader("🔔 Alertas de Gestão")
c_a1, c_a2 = st.columns(2)
v_pendente = float(df_master[df_master['status']=='pendente']['valor_bruto'].sum())
with c_a1:
    if v_pendente > 1000: st.warning(f"Atenção: R$ {v_pendente:,.2f} em guias abertas.")
    else: st.success("Saúde fiscal em dia.")
with c_a2:
    if saldo_at > 5000: st.info(f"Capitalização Ativa: O saldo atual pode render R$ {saldo_at*0.00043:,.2f} nas próximas 24h.")

st.divider()
tabs = st.tabs(["📈 Insights", "📥 Operacional", "💰 Saques e Relatórios", "📅 Planejamento"])

# --- ABA 3: FINANCEIRO ---
with tabs[2]:
    df_ex = df_master[df_master['status']=='pago']
    res = obter_resumo_auditoria(mun_id)
    e1, e2, e3 = st.columns([1,1,2])
    with e1:
        if not df_ex.empty:
            try:
                pdf_b = gerar_pdf_oficial(option, df_ex, res)
                st.download_button("📄 Baixar Relatório PDF", pdf_b, f"relatorio_{option}.pdf", "application/pdf")
            except: st.error("Erro ao gerar PDF")
    with e2:
        csv = df_ex.to_csv(index=False).encode('utf-8')
        st.download_button("📊 Exportar CSV", csv, "extrato.csv", "text/csv")
    
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Saldo Custódia", f"R$ {saldo_at:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m2.metric("Taxas Assat", f"R$ {len(df_ex[df_ex['valor_bruto']>0])*0.90:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m3.metric("Rendimento/Dia", f"R$ {saldo_at*0.00043:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    
    st.subheader("Solicitar Resgate")
    v_s = st.number_input("Valor Saque", 0.0, max_value=saldo_at)
    if st.button("Confirmar Saque"):
        suc, msg = registrar_saque(mun_id, v_s)
        if suc: st.success(msg); st.rerun()
        else: st.error(msg)

# --- ABA 4: PLANEJAMENTO (COM BALÃO DE VALOR TOTAL) ---
with tabs[3]:
    st.subheader("📅 Simulador de Capitalização Assat")
    st.info("Ajuste o período para visualizar o crescimento patrimonial do município.")
    
    col_par, col_fig = st.columns([1, 2])
    
    # Cálculo de Rentabilidade
    taxa_selic_anual = 0.1325 # 13.25%
    taxa_diaria = (1 + taxa_selic_anual)**(1/252) - 1

    with col_par:
        dias_p = st.slider("Dias de Permanência", 1, 365, 30)
        
        # O "BALÃO" DE VALOR TOTAL
        proj_final = saldo_at * (1 + taxa_diaria)**dias_p
        lucro_proj = proj_final - saldo_at
        
        st.markdown(f"""
            <div style="background-color:#e1f5fe; padding:20px; border-radius:10px; border-left: 5px solid #0288d1; margin-bottom:20px;">
                <h4 style="color:#01579b; margin:0;">Projeção Final ({dias_p} dias)</h4>
                <h2 style="color:#0288d1; margin:10px 0;">R$ {proj_final:,.2f}</h2>
                <p style="color:#01579b; margin:0;"><b>Ganho estimado:</b> R$ {lucro_proj:,.2f}</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.write(f"Rentabilidade baseada em CDI 100% ({taxa_selic_anual*100}% a.a.)")

    with col_fig:
        datas_p = [(datetime.now() + timedelta(days=i)) for i in range(dias_p+1)]
        valores_p = [saldo_at * (1 + taxa_diaria)**i for i in range(dias_p+1)]
        fig_p = px.line(x=datas_p, y=valores_p, title="Evolução do Montante", labels={'x':'Data','y':'Saldo (R$)'})
        fig_p.update_yaxes(range=[saldo_at*0.99, max(valores_p)*1.01])
        fig_p.update_traces(line_color='#0288d1', line_width=3)
        st.plotly_chart(fig_p, use_container_width=True)

# Re-inserindo abas faltantes para integridade do código
with tabs[0]:
    df_pg = df_master[(df_master['status']=='pago') & (df_master['valor_bruto']>0)]
    if not df_pg.empty:
        g1, g2 = st.columns(2)
        g1.plotly_chart(px.pie(df_pg, values='valor_bruto', names='tipo_tributo', hole=.4, title="Tributos"), use_container_width=True)
        g2.plotly_chart(px.pie(df_pg, values='valor_bruto', names='metodo_pagamento', hole=.4, title="Meios"), use_container_width=True)
with tabs[1]:
    o1, o2 = st.columns([1,2])
    with o1:
        with st.form("guia"):
            t = st.selectbox("Tributo", ["IPTU", "ISS", "Taxas"])
            v = st.number_input("Valor", 1.0)
            m = st.selectbox("Meio", ["Pix", "Boleto", "Cartão"])
            if st.form_submit_button("Gerar"): criar_cobranca(mun_id, t, v, m); st.rerun()
    with o2:
        df_p = df_master[df_master['status']=='pendente']
        st.dataframe(df_p[['id', 'tipo_tributo', 'valor_bruto']], use_container_width=True, hide_index=True)
        id_bx = st.number_input("ID Baixa", 0)
        if st.button("Confirmar Recebimento"): registrar_pagamento(int(id_bx)); st.rerun()