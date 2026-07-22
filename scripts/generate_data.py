#!/usr/bin/env python3
"""
Gerador de dados sintéticos históricos — JSTechStore Brasil.

Cria todos os schemas/tabelas no Supabase e popula com 3 anos de histórico:
  • 15 lojas físicas + e-commerce + centro de distribuição
  • ~125 SKUs ativos em 5 categorias de tecnologia
  • 100.000 clientes cadastrados com crescimento gradual
  • ~2.000 pedidos/dia com sazonalidade realista (Black Friday 5×, Natal 2,5×)

Uso:
    python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42
    python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42 --skip-ddl
    python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42 --force
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from faker import Faker
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

fake = Faker("pt_BR")

# ─────────────────────────────────────────────────────────────────────────────
# Dados mestres — lojas
# ─────────────────────────────────────────────────────────────────────────────

LOJAS: list[dict] = [
    {"codigo": "POA01", "nome_loja": "JSTechStore Porto Alegre Centro",   "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Porto Alegre",   "uf": "RS", "gerente": "Carlos Eduardo Machado",  "capacidade_m2": 450,  "dt_abertura": "2018-03-15"},
    {"codigo": "POA02", "nome_loja": "JSTechStore Porto Alegre Sul",      "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Porto Alegre",   "uf": "RS", "gerente": "Fernanda Lima Costa",      "capacidade_m2": 380,  "dt_abertura": "2019-08-22"},
    {"codigo": "CXS01", "nome_loja": "JSTechStore Caxias do Sul",         "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Caxias do Sul",  "uf": "RS", "gerente": "Roberto Nunes Junior",     "capacidade_m2": 320,  "dt_abertura": "2020-01-10"},
    {"codigo": "FLN01", "nome_loja": "JSTechStore Florianópolis",         "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Florianópolis",  "uf": "SC", "gerente": "Patrícia Souza",           "capacidade_m2": 400,  "dt_abertura": "2018-07-01"},
    {"codigo": "JOI01", "nome_loja": "JSTechStore Joinville",             "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Joinville",      "uf": "SC", "gerente": "Alexandre Pereira",        "capacidade_m2": 290,  "dt_abertura": "2021-03-05"},
    {"codigo": "CWB01", "nome_loja": "JSTechStore Curitiba Centro",       "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Curitiba",       "uf": "PR", "gerente": "Mariana Oliveira",         "capacidade_m2": 500,  "dt_abertura": "2017-11-20"},
    {"codigo": "CWB02", "nome_loja": "JSTechStore Curitiba Batel",        "tipo_loja": "fisica",    "regiao": "Sul",          "cidade": "Curitiba",       "uf": "PR", "gerente": "Thiago Alves Santos",      "capacidade_m2": 420,  "dt_abertura": "2020-06-14"},
    {"codigo": "SPO01", "nome_loja": "JSTechStore São Paulo Paulista",    "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "São Paulo",      "uf": "SP", "gerente": "Ana Paula Ferreira",       "capacidade_m2": 600,  "dt_abertura": "2015-04-18"},
    {"codigo": "SPO02", "nome_loja": "JSTechStore São Paulo Morumbi",     "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "São Paulo",      "uf": "SP", "gerente": "Lucas Mendes",             "capacidade_m2": 520,  "dt_abertura": "2017-09-30"},
    {"codigo": "SPO03", "nome_loja": "JSTechStore Santo André",           "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "Santo André",    "uf": "SP", "gerente": "Juliana Rodrigues",        "capacidade_m2": 350,  "dt_abertura": "2019-02-14"},
    {"codigo": "CPQ01", "nome_loja": "JSTechStore Campinas",              "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "Campinas",       "uf": "SP", "gerente": "Ricardo Barbosa",          "capacidade_m2": 390,  "dt_abertura": "2020-11-01"},
    {"codigo": "RIO01", "nome_loja": "JSTechStore Rio de Janeiro Centro", "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "Rio de Janeiro", "uf": "RJ", "gerente": "Beatriz Santos Almeida",   "capacidade_m2": 480,  "dt_abertura": "2016-05-22"},
    {"codigo": "RIO02", "nome_loja": "JSTechStore Rio Barra da Tijuca",   "tipo_loja": "fisica",    "regiao": "Sudeste",      "cidade": "Rio de Janeiro", "uf": "RJ", "gerente": "Gustavo Marques",          "capacidade_m2": 440,  "dt_abertura": "2021-08-10"},
    {"codigo": "BSB01", "nome_loja": "JSTechStore Brasília",              "tipo_loja": "fisica",    "regiao": "Centro-Oeste", "cidade": "Brasília",       "uf": "DF", "gerente": "Camila Torres",            "capacidade_m2": 420,  "dt_abertura": "2019-04-25"},
    {"codigo": "GYN01", "nome_loja": "JSTechStore Goiânia",               "tipo_loja": "fisica",    "regiao": "Centro-Oeste", "cidade": "Goiânia",        "uf": "GO", "gerente": "Felipe Carvalho",          "capacidade_m2": 360,  "dt_abertura": "2022-01-15"},
    {"codigo": "ECOM",  "nome_loja": "JSTechStore E-commerce",            "tipo_loja": "ecommerce", "regiao": "Nacional",     "cidade": "Porto Alegre",   "uf": "RS", "gerente": "Diego Almeida",            "capacidade_m2": None, "dt_abertura": "2015-01-01"},
    {"codigo": "CD01",  "nome_loja": "JSTechStore CD Porto Alegre",       "tipo_loja": "cd",        "regiao": "Sul",          "cidade": "Porto Alegre",   "uf": "RS", "gerente": "Silvia Monteiro",          "capacidade_m2": 2000, "dt_abertura": "2015-01-01"},
]

CATEGORIAS: list[dict] = [
    {"nome": "Smartphones e Tablets",    "subcategoria": "Eletrônicos Pessoais"},
    {"nome": "Notebooks e Desktops",     "subcategoria": "Computadores"},
    {"nome": "Games e Consoles",         "subcategoria": "Entretenimento Digital"},
    {"nome": "TVs e Áudio",              "subcategoria": "Entretenimento em Casa"},
    {"nome": "Periféricos e Acessórios", "subcategoria": "Computadores"},
]

FORNECEDORES: list[dict] = [
    {"nome_fornecedor": "Samsung Electronics Brasil",    "cnpj": "07.600.156/0001-06", "categoria_principal": "Smartphones e Tablets",    "pais_origem": "Coreia do Sul",  "prazo_entrega_dias": 21},
    {"nome_fornecedor": "Apple Brasil Ltda",             "cnpj": "00.623.904/0001-73", "categoria_principal": "Smartphones e Tablets",    "pais_origem": "Estados Unidos", "prazo_entrega_dias": 30},
    {"nome_fornecedor": "Motorola Industrial Ltda",      "cnpj": "63.082.491/0001-00", "categoria_principal": "Smartphones e Tablets",    "pais_origem": "Brasil",         "prazo_entrega_dias": 14},
    {"nome_fornecedor": "Lenovo do Brasil",              "cnpj": "08.282.330/0001-24", "categoria_principal": "Notebooks e Desktops",     "pais_origem": "China",          "prazo_entrega_dias": 25},
    {"nome_fornecedor": "Dell Computadores do Brasil",   "cnpj": "72.381.189/0001-10", "categoria_principal": "Notebooks e Desktops",     "pais_origem": "Brasil",         "prazo_entrega_dias": 18},
    {"nome_fornecedor": "Sony Brasil Ltda",              "cnpj": "58.157.462/0001-89", "categoria_principal": "TVs e Áudio",              "pais_origem": "Japão",          "prazo_entrega_dias": 28},
    {"nome_fornecedor": "LG Eletronics Brasil",          "cnpj": "09.168.704/0001-89", "categoria_principal": "TVs e Áudio",              "pais_origem": "Coreia do Sul",  "prazo_entrega_dias": 21},
    {"nome_fornecedor": "Microsoft Games Brasil",        "cnpj": "60.316.817/0001-68", "categoria_principal": "Games e Consoles",         "pais_origem": "Estados Unidos", "prazo_entrega_dias": 25},
    {"nome_fornecedor": "Nintendo Brasil Ltda",          "cnpj": "97.094.983/0001-71", "categoria_principal": "Games e Consoles",         "pais_origem": "Japão",          "prazo_entrega_dias": 30},
    {"nome_fornecedor": "Logitech Brasil",               "cnpj": "04.082.680/0001-03", "categoria_principal": "Periféricos e Acessórios", "pais_origem": "Suíça",          "prazo_entrega_dias": 20},
]

# (nome, marca, categoria, custo_min, custo_max, margem_min, margem_max, peso_kg)
PRODUTOS_CATALOG: list[tuple] = [
    # Smartphones e Tablets
    ("Samsung Galaxy A34 128GB",             "Samsung",  "Smartphones e Tablets",    700,  800,  0.25, 0.35, 0.19),
    ("Samsung Galaxy A54 256GB",             "Samsung",  "Smartphones e Tablets",    900,  1050, 0.25, 0.35, 0.20),
    ("Samsung Galaxy S23 256GB",             "Samsung",  "Smartphones e Tablets",   2800,  3200, 0.22, 0.32, 0.17),
    ("Samsung Galaxy S23 Ultra 512GB",       "Samsung",  "Smartphones e Tablets",   5500,  6500, 0.20, 0.30, 0.23),
    ("Samsung Galaxy Tab S8 256GB Wi-Fi",    "Samsung",  "Smartphones e Tablets",   1800,  2100, 0.22, 0.32, 0.50),
    ("iPhone 13 128GB",                      "Apple",    "Smartphones e Tablets",   2400,  2800, 0.25, 0.35, 0.17),
    ("iPhone 14 128GB",                      "Apple",    "Smartphones e Tablets",   3500,  4000, 0.22, 0.30, 0.17),
    ("iPhone 14 Pro 256GB",                  "Apple",    "Smartphones e Tablets",   5000,  5800, 0.20, 0.28, 0.20),
    ("iPhone 15 128GB",                      "Apple",    "Smartphones e Tablets",   4800,  5500, 0.20, 0.28, 0.17),
    ("iPhone 15 Pro Max 256GB",              "Apple",    "Smartphones e Tablets",   7500,  8500, 0.18, 0.25, 0.22),
    ("iPad 10ª Geração 64GB Wi-Fi",          "Apple",    "Smartphones e Tablets",   1500,  1800, 0.22, 0.30, 0.48),
    ("Motorola Edge 40 256GB",               "Motorola", "Smartphones e Tablets",   1400,  1700, 0.25, 0.35, 0.17),
    ("Motorola Moto G84 256GB",              "Motorola", "Smartphones e Tablets",    700,   900, 0.28, 0.38, 0.17),
    ("Xiaomi 13T 256GB",                     "Xiaomi",   "Smartphones e Tablets",   1600,  2000, 0.25, 0.35, 0.19),
    ("Xiaomi Redmi Note 12 128GB",           "Xiaomi",   "Smartphones e Tablets",    550,   700, 0.28, 0.40, 0.18),
    # Notebooks e Desktops
    ("Dell Inspiron 15 i5 8GB 512GB SSD",    "Dell",     "Notebooks e Desktops",    1800,  2200, 0.18, 0.28, 1.85),
    ("Dell Inspiron 15 i7 16GB 512GB SSD",   "Dell",     "Notebooks e Desktops",    2600,  3100, 0.18, 0.26, 1.90),
    ("Dell XPS 13 i7 16GB 512GB SSD",        "Dell",     "Notebooks e Desktops",    5000,  6000, 0.18, 0.25, 1.25),
    ("Dell XPS 15 i7 32GB 1TB SSD",          "Dell",     "Notebooks e Desktops",    7000,  8500, 0.15, 0.22, 1.85),
    ("Lenovo IdeaPad 3 i5 8GB 256GB SSD",    "Lenovo",   "Notebooks e Desktops",    1400,  1700, 0.18, 0.28, 1.65),
    ("Lenovo IdeaPad 5 i7 16GB 512GB SSD",   "Lenovo",   "Notebooks e Desktops",    2800,  3400, 0.18, 0.26, 1.75),
    ("Lenovo ThinkPad E15 i5 16GB 512GB",    "Lenovo",   "Notebooks e Desktops",    3000,  3600, 0.20, 0.28, 1.85),
    ("Acer Aspire 5 i5 8GB 512GB SSD",       "Acer",     "Notebooks e Desktops",    1500,  1900, 0.18, 0.28, 1.80),
    ("Acer Nitro 5 i5 16GB 512GB RTX3050",   "Acer",     "Notebooks e Desktops",    3200,  3800, 0.20, 0.28, 2.20),
    ("HP Pavilion 15 i5 8GB 512GB SSD",      "HP",       "Notebooks e Desktops",    1600,  2000, 0.18, 0.28, 1.75),
    ("HP Envy 13 i7 16GB 512GB SSD",         "HP",       "Notebooks e Desktops",    4000,  5000, 0.18, 0.25, 1.32),
    ("ASUS VivoBook 15 i5 16GB 512GB SSD",   "ASUS",     "Notebooks e Desktops",    2000,  2500, 0.18, 0.28, 1.75),
    ("ASUS ROG Strix i7 32GB 1TB RTX4060",   "ASUS",     "Notebooks e Desktops",    7000,  8000, 0.18, 0.25, 2.40),
    ("Samsung Galaxy Book3 Pro i7 16GB",     "Samsung",  "Notebooks e Desktops",    4500,  5500, 0.20, 0.28, 1.35),
    # Games e Consoles
    ("PlayStation 5 Standard Edition",       "Sony",     "Games e Consoles",        2800,  3200, 0.20, 0.30, 3.90),
    ("PlayStation 5 Digital Edition",        "Sony",     "Games e Consoles",        2400,  2800, 0.20, 0.30, 3.60),
    ("Xbox Series X 1TB",                    "Microsoft","Games e Consoles",         2600,  3000, 0.20, 0.30, 4.45),
    ("Xbox Series S 512GB Carbon Black",     "Microsoft","Games e Consoles",         1300,  1600, 0.22, 0.32, 1.93),
    ("Nintendo Switch OLED 64GB",            "Nintendo", "Games e Consoles",        1600,  1900, 0.20, 0.30, 0.42),
    ("Nintendo Switch Lite",                 "Nintendo", "Games e Consoles",         900,  1100, 0.22, 0.32, 0.28),
    ("God of War Ragnarök PS5",              "Sony",     "Games e Consoles",         160,   200, 0.30, 0.45, 0.10),
    ("Marvel's Spider-Man 2 PS5",            "Sony",     "Games e Consoles",         180,   220, 0.30, 0.45, 0.10),
    ("Call of Duty Modern Warfare III",      "Microsoft","Games e Consoles",          180,   220, 0.30, 0.45, 0.10),
    ("FIFA 24",                              "EA Sports","Games e Consoles",          150,   190, 0.30, 0.45, 0.10),
    ("Zelda Tears of the Kingdom Switch",    "Nintendo", "Games e Consoles",         160,   200, 0.28, 0.42, 0.10),
    ("Controle DualSense PS5",               "Sony",     "Games e Consoles",         280,   360, 0.25, 0.38, 0.28),
    ("Headset Sony PULSE 3D Wireless",       "Sony",     "Games e Consoles",         400,   500, 0.25, 0.38, 0.35),
    # TVs e Áudio
    ("Samsung Smart TV 50\" Crystal UHD 4K", "Samsung",  "TVs e Áudio",             1500,  1900, 0.20, 0.30, 11.0),
    ("Samsung Smart TV 55\" QLED 4K Q60C",   "Samsung",  "TVs e Áudio",             2200,  2700, 0.20, 0.30, 14.0),
    ("Samsung Smart TV 65\" QLED 4K Q70C",   "Samsung",  "TVs e Áudio",             3800,  4500, 0.18, 0.28, 18.0),
    ("LG Smart TV 55\" OLED evo C3 4K",      "LG",       "TVs e Áudio",             3500,  4200, 0.18, 0.28, 15.5),
    ("LG Smart TV 65\" OLED evo C3 4K",      "LG",       "TVs e Áudio",             5500,  6500, 0.18, 0.25, 22.0),
    ("LG Smart TV 43\" NanoCell 4K",         "LG",       "TVs e Áudio",             1100,  1400, 0.20, 0.30,  9.0),
    ("Sony Bravia 55\" X85L 4K Google TV",   "Sony",     "TVs e Áudio",             2500,  3000, 0.20, 0.28, 14.5),
    ("Sony Bravia 65\" X90L 4K Google TV",   "Sony",     "TVs e Áudio",             4500,  5500, 0.18, 0.25, 24.0),
    ("JBL Charge 5 Bluetooth",               "JBL",      "TVs e Áudio",              350,   450, 0.38, 0.52,  0.96),
    ("JBL Flip 6 Bluetooth",                 "JBL",      "TVs e Áudio",              250,   320, 0.38, 0.52,  0.53),
    ("Sony WH-1000XM5 Headphone NC",         "Sony",     "TVs e Áudio",              900,  1100, 0.30, 0.42,  0.25),
    ("Bose QuietComfort 45 Headphone",       "Bose",     "TVs e Áudio",             1400,  1700, 0.28, 0.40,  0.24),
    ("Samsung Soundbar Q990C 11.1.4ch",      "Samsung",  "TVs e Áudio",             2500,  3000, 0.20, 0.30,  7.20),
    # Periféricos e Acessórios
    ("Logitech MX Master 3S Mouse",           "Logitech","Periféricos e Acessórios",  200,   260, 0.42, 0.58, 0.14),
    ("Logitech G Pro X Superlight 2 Mouse",   "Logitech","Periféricos e Acessórios",  280,   350, 0.40, 0.55, 0.06),
    ("Razer DeathAdder V3 Mouse",             "Razer",   "Periféricos e Acessórios",  220,   280, 0.40, 0.55, 0.06),
    ("Logitech MX Keys Teclado Wireless",     "Logitech","Periféricos e Acessórios",  290,   380, 0.40, 0.55, 0.81),
    ("Razer Huntsman V2 Teclado Mecânico",    "Razer",   "Periféricos e Acessórios",  380,   490, 0.38, 0.52, 1.02),
    ("SteelSeries Arctis 7 Headset Wireless", "SteelSeries","Periféricos e Acessórios",320, 420, 0.38, 0.52, 0.35),
    ("HyperX Cloud II Wireless Headset",      "HyperX",  "Periféricos e Acessórios",  280,   360, 0.38, 0.52, 0.32),
    ("Logitech C920 Webcam HD Pro",           "Logitech","Periféricos e Acessórios",  200,   260, 0.40, 0.55, 0.16),
    ("Samsung T7 SSD Externo 1TB USB",        "Samsung", "Periféricos e Acessórios",  200,   260, 0.38, 0.52, 0.06),
    ("WD My Passport 2TB USB 3.0",            "WD",      "Periféricos e Acessórios",  220,   280, 0.35, 0.50, 0.14),
    ("Anker Carregador GaN 65W USB-C",        "Anker",   "Periféricos e Acessórios",   60,    90, 0.50, 0.70, 0.10),
    ("Belkin Hub USB-C 7 portas",             "Belkin",  "Periféricos e Acessórios",   90,   130, 0.48, 0.65, 0.18),
    ("Mouse Pad Desk Pad XL 90×40cm",         "Redragon","Periféricos e Acessórios",   35,    60, 0.55, 0.75, 0.40),
    ("Cabo HDMI 2.1 Premium 2m",              "Intelbras","Periféricos e Acessórios",  25,    50, 0.55, 0.75, 0.18),
]

TRANSPORTADORAS: list[dict] = [
    {"nome": "Correios",             "cnpj": "34.028.316/0001-03", "prazo_dias_min": 3, "prazo_dias_max": 15},
    {"nome": "Jadlog",               "cnpj": "04.884.082/0001-35", "prazo_dias_min": 2, "prazo_dias_max": 7},
    {"nome": "Total Express",        "cnpj": "02.952.301/0001-00", "prazo_dias_min": 2, "prazo_dias_max": 5},
    {"nome": "Frota Própria JSTech", "cnpj": "99.999.001/0001-01", "prazo_dias_min": 0, "prazo_dias_max": 1},
    {"nome": "Mercado Envios",       "cnpj": "03.007.331/0001-41", "prazo_dias_min": 2, "prazo_dias_max": 10},
]

# (codigo, nome, transportadora, prazo_dias, frete_base, tipo)
MODALIDADES: list[tuple] = [
    ("SEDEX",    "SEDEX Correios",          "Correios",             3,  18.0, "correios"),
    ("PAC",      "PAC Correios",            "Correios",             8,   9.0, "correios"),
    ("JADLOG_E", "Jadlog Econômico",        "Jadlog",               5,  12.0, "privado"),
    ("JADLOG_E2","Jadlog Expresso",         "Jadlog",               2,  22.0, "privado"),
    ("TOTEX",    "Total Express Expresso",  "Total Express",        2,  20.0, "privado"),
    ("SAME_DAY", "Same Day Frota Própria",  "Frota Própria JSTech", 0,  15.0, "loja"),
    ("RETIRADA", "Retirada na Loja",        "Frota Própria JSTech", 0,   0.0, "loja"),
    ("ML_ENV",   "Mercado Envios Full",     "Mercado Envios",       4,  10.0, "marketplace"),
]

METODOS_PAGAMENTO = ["cartao_credito", "cartao_debito", "pix", "boleto", "cartao_credito", "cartao_credito"]
CANAIS = ["loja_fisica", "site_proprio", "marketplace_ml", "marketplace_amazon", "marketplace_shopee"]
CANAIS_PESOS = [0.38, 0.25, 0.17, 0.12, 0.08]
NIVEIS_FIDELIDADE = ["Bronze", "Silver", "Gold", "Platinum"]
MOTIVOS_DEVOLUCAO = ["produto_defeituoso", "nao_correspondeu_descricao", "arrependimento", "produto_errado", "dano_transporte"]
ESTADOS_BR = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "CE", "GO", "DF", "PE", "AM", "PA", "MT", "MS"]
ESTADOS_PESOS = [0.22, 0.15, 0.12, 0.10, 0.09, 0.07, 0.05, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.01]

# ─────────────────────────────────────────────────────────────────────────────
# DDL — schemas e tabelas
# ─────────────────────────────────────────────────────────────────────────────

DDL = """
CREATE SCHEMA IF NOT EXISTS vendas;
CREATE SCHEMA IF NOT EXISTS clientes;
CREATE SCHEMA IF NOT EXISTS produtos;
CREATE SCHEMA IF NOT EXISTS estoque;
CREATE SCHEMA IF NOT EXISTS logistica;
CREATE SCHEMA IF NOT EXISTS financeiro;
CREATE SCHEMA IF NOT EXISTS marketing;
CREATE SCHEMA IF NOT EXISTS rh;
CREATE SCHEMA IF NOT EXISTS web_analytics;

CREATE TABLE IF NOT EXISTS rh.lojas (
    id_loja        SERIAL PRIMARY KEY,
    codigo         VARCHAR(10)  UNIQUE NOT NULL,
    nome_loja      VARCHAR(100) NOT NULL,
    tipo_loja      VARCHAR(20)  NOT NULL,
    regiao         VARCHAR(30)  NOT NULL,
    cidade         VARCHAR(100) NOT NULL,
    uf             CHAR(2)      NOT NULL,
    gerente        VARCHAR(100),
    capacidade_m2  INT,
    dt_abertura    DATE         NOT NULL,
    ativo          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clientes.clientes (
    id_cliente       SERIAL PRIMARY KEY,
    cpf              VARCHAR(14)  UNIQUE NOT NULL,
    email            VARCHAR(255) UNIQUE NOT NULL,
    telefone         VARCHAR(20),
    primeiro_nome    VARCHAR(100) NOT NULL,
    nome_completo    VARCHAR(255) NOT NULL,
    cep              VARCHAR(9),
    cidade           VARCHAR(100),
    uf               CHAR(2),
    data_cadastro    DATE         NOT NULL,
    canal_origem     VARCHAR(30),
    nivel_fidelidade VARCHAR(20)  NOT NULL DEFAULT 'Bronze',
    ativo            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clientes.enderecos (
    id_endereco  SERIAL PRIMARY KEY,
    id_cliente   INT          NOT NULL REFERENCES clientes.clientes(id_cliente),
    logradouro   VARCHAR(255),
    numero       VARCHAR(20),
    complemento  VARCHAR(100),
    bairro       VARCHAR(100),
    cep          VARCHAR(9),
    cidade       VARCHAR(100),
    uf           CHAR(2),
    tipo         VARCHAR(20)  NOT NULL DEFAULT 'principal',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clientes.techpoints (
    id_techpoints     SERIAL PRIMARY KEY,
    id_cliente        INT         UNIQUE NOT NULL REFERENCES clientes.clientes(id_cliente),
    pontos_acumulados INT         NOT NULL DEFAULT 0,
    pontos_resgatados INT         NOT NULL DEFAULT 0,
    saldo_pontos      INT         NOT NULL DEFAULT 0,
    nivel_fidelidade  VARCHAR(20) NOT NULL DEFAULT 'Bronze',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos.categorias (
    id_categoria SERIAL PRIMARY KEY,
    nome         VARCHAR(100) UNIQUE NOT NULL,
    subcategoria VARCHAR(100),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos.fornecedores (
    id_fornecedor       SERIAL PRIMARY KEY,
    nome_fornecedor     VARCHAR(200) UNIQUE NOT NULL,
    cnpj                VARCHAR(18),
    categoria_principal VARCHAR(100),
    pais_origem         VARCHAR(50)  NOT NULL DEFAULT 'Brasil',
    prazo_entrega_dias  INT          NOT NULL DEFAULT 30,
    ativo               BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos.produtos (
    id_produto   SERIAL PRIMARY KEY,
    id_categoria INT          NOT NULL REFERENCES produtos.categorias(id_categoria),
    id_fornecedor INT         NOT NULL REFERENCES produtos.fornecedores(id_fornecedor),
    sku          VARCHAR(30)  UNIQUE NOT NULL,
    nome         VARCHAR(200) NOT NULL,
    marca        VARCHAR(100) NOT NULL,
    peso_kg      NUMERIC(8,3) NOT NULL DEFAULT 0.5,
    ativo        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos.precos (
    id_preco            SERIAL PRIMARY KEY,
    id_produto          INT           NOT NULL REFERENCES produtos.produtos(id_produto),
    preco_venda         NUMERIC(12,2) NOT NULL,
    custo_unitario      NUMERIC(12,2) NOT NULL,
    dt_vigencia_inicio  DATE          NOT NULL,
    dt_vigencia_fim     DATE,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (id_produto, dt_vigencia_inicio)
);

CREATE TABLE IF NOT EXISTS logistica.transportadoras (
    id_transportadora SERIAL PRIMARY KEY,
    nome              VARCHAR(100) UNIQUE NOT NULL,
    cnpj              VARCHAR(18),
    prazo_dias_min    INT          NOT NULL DEFAULT 1,
    prazo_dias_max    INT          NOT NULL DEFAULT 10,
    ativo             BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logistica.modalidades (
    id_modalidade     SERIAL PRIMARY KEY,
    id_transportadora INT           NOT NULL REFERENCES logistica.transportadoras(id_transportadora),
    nome              VARCHAR(100)  NOT NULL,
    codigo            VARCHAR(20)   UNIQUE NOT NULL,
    prazo_dias        INT           NOT NULL DEFAULT 5,
    frete_base        NUMERIC(10,2) NOT NULL DEFAULT 0,
    tipo              VARCHAR(20)   NOT NULL DEFAULT 'privado',
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rh.vendedores (
    id_vendedor    SERIAL PRIMARY KEY,
    id_loja        INT          NOT NULL REFERENCES rh.lojas(id_loja),
    nome           VARCHAR(200) NOT NULL,
    cpf            VARCHAR(14)  UNIQUE NOT NULL,
    email          VARCHAR(255),
    cargo          VARCHAR(50)  NOT NULL DEFAULT 'vendedor',
    data_admissao  DATE         NOT NULL,
    ativo          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS marketing.campanhas (
    id_campanha  SERIAL PRIMARY KEY,
    nome         VARCHAR(200) NOT NULL,
    tipo         VARCHAR(50)  NOT NULL,
    canal        VARCHAR(50)  NOT NULL DEFAULT 'email',
    dt_inicio    DATE         NOT NULL,
    dt_fim       DATE         NOT NULL,
    orcamento    NUMERIC(12,2),
    objetivo     VARCHAR(50)  NOT NULL DEFAULT 'conversao',
    ativo        BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financeiro.orcamentos (
    id_orcamento         SERIAL PRIMARY KEY,
    id_loja              INT           NOT NULL REFERENCES rh.lojas(id_loja),
    canal_venda          VARCHAR(30)   NOT NULL,
    ano                  INT           NOT NULL,
    mes                  INT           NOT NULL,
    valor_meta_receita   NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_meta_margem    NUMERIC(14,2) NOT NULL DEFAULT 0,
    qtd_meta_pedidos     INT           NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vendas.pedidos (
    id_pedido          SERIAL PRIMARY KEY,
    id_cliente         INT           NOT NULL REFERENCES clientes.clientes(id_cliente),
    id_loja            INT           NOT NULL REFERENCES rh.lojas(id_loja),
    canal_venda        VARCHAR(30)   NOT NULL,
    status             VARCHAR(30)   NOT NULL DEFAULT 'confirmado',
    dt_pedido          TIMESTAMPTZ   NOT NULL,
    dt_confirmacao     TIMESTAMPTZ,
    dt_cancelamento    TIMESTAMPTZ,
    valor_bruto        NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_desconto     NUMERIC(12,2) NOT NULL DEFAULT 0,
    valor_frete        NUMERIC(10,2) NOT NULL DEFAULT 0,
    valor_liquido      NUMERIC(12,2) NOT NULL DEFAULT 0,
    parcelas           INT           NOT NULL DEFAULT 1,
    metodo_pagamento   VARCHAR(30)   NOT NULL DEFAULT 'pix',
    cupom              VARCHAR(50),
    id_campanha        INT           REFERENCES marketing.campanhas(id_campanha),
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vendas.itens_pedido (
    id_item_pedido    SERIAL PRIMARY KEY,
    id_pedido         INT           NOT NULL REFERENCES vendas.pedidos(id_pedido),
    id_produto        INT           NOT NULL REFERENCES produtos.produtos(id_produto),
    qtd_vendida       INT           NOT NULL DEFAULT 1,
    preco_unitario    NUMERIC(12,2) NOT NULL,
    custo_unitario    NUMERIC(12,2) NOT NULL,
    desconto_item     NUMERIC(10,2) NOT NULL DEFAULT 0,
    valor_liquido_item NUMERIC(12,2) NOT NULL,
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vendas.devolucoes (
    id_devolucao   SERIAL PRIMARY KEY,
    id_pedido      INT           NOT NULL REFERENCES vendas.pedidos(id_pedido),
    id_produto     INT           NOT NULL REFERENCES produtos.produtos(id_produto),
    dt_devolucao   DATE          NOT NULL,
    motivo         VARCHAR(100)  NOT NULL,
    qtd_devolvida  INT           NOT NULL DEFAULT 1,
    valor_devolvido NUMERIC(12,2) NOT NULL DEFAULT 0,
    status         VARCHAR(30)   NOT NULL DEFAULT 'aprovada',
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logistica.entregas (
    id_entrega        SERIAL PRIMARY KEY,
    id_pedido         INT          UNIQUE NOT NULL REFERENCES vendas.pedidos(id_pedido),
    id_transportadora INT          NOT NULL REFERENCES logistica.transportadoras(id_transportadora),
    id_modalidade     INT          NOT NULL REFERENCES logistica.modalidades(id_modalidade),
    id_loja_origem    INT          NOT NULL REFERENCES rh.lojas(id_loja),
    codigo_rastreio   VARCHAR(50),
    dt_postagem       DATE,
    dt_promessa       DATE         NOT NULL,
    dt_efetiva        DATE,
    fl_sla_atendido   BOOLEAN,
    status            VARCHAR(30)  NOT NULL DEFAULT 'em_transito',
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS estoque.saldo_estoque (
    id_saldo              SERIAL PRIMARY KEY,
    id_produto            INT         NOT NULL REFERENCES produtos.produtos(id_produto),
    id_loja               INT         NOT NULL REFERENCES rh.lojas(id_loja),
    qtd_disponivel        INT         NOT NULL DEFAULT 0,
    qtd_reservada         INT         NOT NULL DEFAULT 0,
    qtd_minima            INT         NOT NULL DEFAULT 5,
    dt_ultima_atualizacao DATE        NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id_produto, id_loja)
);

CREATE TABLE IF NOT EXISTS estoque.movimentacoes (
    id_movimentacao  SERIAL PRIMARY KEY,
    id_produto       INT           NOT NULL REFERENCES produtos.produtos(id_produto),
    id_loja          INT           NOT NULL REFERENCES rh.lojas(id_loja),
    tipo_mov         VARCHAR(30)   NOT NULL,
    qtd              INT           NOT NULL,
    dt_movimentacao  TIMESTAMPTZ   NOT NULL,
    id_pedido        INT           REFERENCES vendas.pedidos(id_pedido),
    custo_unitario   NUMERIC(12,2),
    observacao       VARCHAR(200),
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financeiro.lancamentos (
    id_lancamento  SERIAL PRIMARY KEY,
    id_pedido      INT           REFERENCES vendas.pedidos(id_pedido),
    id_loja        INT           NOT NULL REFERENCES rh.lojas(id_loja),
    tipo           VARCHAR(30)   NOT NULL,
    valor          NUMERIC(12,2) NOT NULL,
    dt_lancamento  DATE          NOT NULL,
    dt_competencia DATE          NOT NULL,
    descricao      VARCHAR(200),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financeiro.parcelas (
    id_parcela      SERIAL PRIMARY KEY,
    id_lancamento   INT           NOT NULL REFERENCES financeiro.lancamentos(id_lancamento),
    numero_parcela  INT           NOT NULL DEFAULT 1,
    valor_parcela   NUMERIC(12,2) NOT NULL,
    dt_vencimento   DATE          NOT NULL,
    dt_pagamento    DATE,
    status          VARCHAR(20)   NOT NULL DEFAULT 'pendente',
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financeiro.contas_receber (
    id_conta        SERIAL PRIMARY KEY,
    id_pedido       INT           NOT NULL REFERENCES vendas.pedidos(id_pedido),
    valor_original  NUMERIC(12,2) NOT NULL,
    valor_pago      NUMERIC(12,2) NOT NULL DEFAULT 0,
    dt_vencimento   DATE          NOT NULL,
    dt_pagamento    DATE,
    status          VARCHAR(20)   NOT NULL DEFAULT 'pendente',
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS marketing.leads (
    id_lead      SERIAL PRIMARY KEY,
    id_campanha  INT          NOT NULL REFERENCES marketing.campanhas(id_campanha),
    id_cliente   INT          REFERENCES clientes.clientes(id_cliente),
    canal        VARCHAR(50)  NOT NULL,
    dt_lead      DATE         NOT NULL,
    convertido   BOOLEAN      NOT NULL DEFAULT FALSE,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS marketing.atribuicao (
    id_atribuicao    SERIAL PRIMARY KEY,
    id_pedido        INT           NOT NULL REFERENCES vendas.pedidos(id_pedido),
    id_campanha      INT           NOT NULL REFERENCES marketing.campanhas(id_campanha),
    canal_atribuicao VARCHAR(50)   NOT NULL,
    tipo_atribuicao  VARCHAR(30)   NOT NULL DEFAULT 'last_click',
    peso             NUMERIC(5,4)  NOT NULL DEFAULT 1.0,
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rh.metas (
    id_meta          SERIAL PRIMARY KEY,
    id_vendedor      INT           NOT NULL REFERENCES rh.vendedores(id_vendedor),
    ano              INT           NOT NULL,
    mes              INT           NOT NULL,
    meta_valor       NUMERIC(12,2) NOT NULL DEFAULT 0,
    meta_qtd_pedidos INT           NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rh.comissoes (
    id_comissao          SERIAL PRIMARY KEY,
    id_vendedor          INT           NOT NULL REFERENCES rh.vendedores(id_vendedor),
    id_pedido            INT           NOT NULL REFERENCES vendas.pedidos(id_pedido),
    valor_venda          NUMERIC(12,2) NOT NULL,
    percentual_comissao  NUMERIC(5,4)  NOT NULL DEFAULT 0.015,
    valor_comissao       NUMERIC(10,2) NOT NULL,
    dt_competencia       DATE          NOT NULL,
    status               VARCHAR(20)   NOT NULL DEFAULT 'pendente',
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_analytics.sessoes (
    id_sessao         SERIAL PRIMARY KEY,
    id_cliente        INT          REFERENCES clientes.clientes(id_cliente),
    canal_origem      VARCHAR(50)  NOT NULL,
    device_type       VARCHAR(20)  NOT NULL DEFAULT 'desktop',
    dt_inicio         TIMESTAMPTZ  NOT NULL,
    dt_fim            TIMESTAMPTZ,
    paginas_visitadas INT          NOT NULL DEFAULT 1,
    converteu         BOOLEAN      NOT NULL DEFAULT FALSE,
    id_pedido         INT          REFERENCES vendas.pedidos(id_pedido),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_analytics.eventos_carrinho (
    id_evento       SERIAL PRIMARY KEY,
    id_sessao       INT           NOT NULL REFERENCES web_analytics.sessoes(id_sessao),
    id_produto      INT           NOT NULL REFERENCES produtos.produtos(id_produto),
    tipo_evento     VARCHAR(30)   NOT NULL,
    dt_evento       TIMESTAMPTZ   NOT NULL,
    qtd             INT           NOT NULL DEFAULT 1,
    preco_na_epoca  NUMERIC(12,2),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clientes_clientes_updated_at     ON clientes.clientes(updated_at);
CREATE INDEX IF NOT EXISTS idx_clientes_enderecos_updated_at    ON clientes.enderecos(updated_at);
CREATE INDEX IF NOT EXISTS idx_clientes_techpoints_updated_at   ON clientes.techpoints(updated_at);
CREATE INDEX IF NOT EXISTS idx_produtos_produtos_updated_at     ON produtos.produtos(updated_at);
CREATE INDEX IF NOT EXISTS idx_produtos_precos_updated_at       ON produtos.precos(updated_at);
CREATE INDEX IF NOT EXISTS idx_produtos_categorias_updated_at   ON produtos.categorias(updated_at);
CREATE INDEX IF NOT EXISTS idx_produtos_fornecedores_updated_at ON produtos.fornecedores(updated_at);
CREATE INDEX IF NOT EXISTS idx_estoque_saldo_updated_at         ON estoque.saldo_estoque(updated_at);
CREATE INDEX IF NOT EXISTS idx_estoque_mov_updated_at           ON estoque.movimentacoes(updated_at);
CREATE INDEX IF NOT EXISTS idx_logistica_entregas_updated_at    ON logistica.entregas(updated_at);
CREATE INDEX IF NOT EXISTS idx_logistica_trans_updated_at       ON logistica.transportadoras(updated_at);
CREATE INDEX IF NOT EXISTS idx_logistica_modal_updated_at       ON logistica.modalidades(updated_at);
CREATE INDEX IF NOT EXISTS idx_financeiro_lanc_updated_at       ON financeiro.lancamentos(updated_at);
CREATE INDEX IF NOT EXISTS idx_financeiro_parc_updated_at       ON financeiro.parcelas(updated_at);
CREATE INDEX IF NOT EXISTS idx_financeiro_cr_updated_at         ON financeiro.contas_receber(updated_at);
CREATE INDEX IF NOT EXISTS idx_financeiro_orc_updated_at        ON financeiro.orcamentos(updated_at);
CREATE INDEX IF NOT EXISTS idx_marketing_camp_updated_at        ON marketing.campanhas(updated_at);
CREATE INDEX IF NOT EXISTS idx_marketing_leads_updated_at       ON marketing.leads(updated_at);
CREATE INDEX IF NOT EXISTS idx_marketing_attr_updated_at        ON marketing.atribuicao(updated_at);
CREATE INDEX IF NOT EXISTS idx_rh_lojas_updated_at              ON rh.lojas(updated_at);
CREATE INDEX IF NOT EXISTS idx_rh_vendedores_updated_at         ON rh.vendedores(updated_at);
CREATE INDEX IF NOT EXISTS idx_rh_metas_updated_at              ON rh.metas(updated_at);
CREATE INDEX IF NOT EXISTS idx_rh_comissoes_updated_at          ON rh.comissoes(updated_at);
CREATE INDEX IF NOT EXISTS idx_vendas_pedidos_updated_at        ON vendas.pedidos(updated_at);
CREATE INDEX IF NOT EXISTS idx_vendas_itens_updated_at          ON vendas.itens_pedido(updated_at);
CREATE INDEX IF NOT EXISTS idx_vendas_dev_updated_at            ON vendas.devolucoes(updated_at);
CREATE INDEX IF NOT EXISTS idx_web_sessoes_updated_at           ON web_analytics.sessoes(updated_at);
CREATE INDEX IF NOT EXISTS idx_web_eventos_updated_at           ON web_analytics.eventos_carrinho(updated_at);
"""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def connect() -> psycopg2.extensions.connection:
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        log.error("SUPABASE_DB_URL não definida. Configure no .env ou como variável de ambiente.")
        sys.exit(1)
    return psycopg2.connect(url)


def bulk_insert(cur, table: str, rows: list[dict], on_conflict: str = "") -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    values = [[r[c] for c in cols] for r in rows]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s {on_conflict}"
    execute_values(cur, sql, values, page_size=500)
    return len(rows)


def rand_ts(dt: date, rng: random.Random, hour_min: int = 8, hour_max: int = 22) -> datetime:
    """Gera timestamp aleatório dentro do horário comercial para um dado dia."""
    h = rng.randint(hour_min, hour_max)
    m = rng.randint(0, 59)
    s = rng.randint(0, 59)
    return datetime(dt.year, dt.month, dt.day, h, m, s, tzinfo=timezone.utc)


def round2(v: float) -> float:
    return round(v, 2)


def seasonality_factor(dt: date, rng: random.Random) -> float:
    """Retorna multiplicador de demanda para a data fornecida."""
    m, d, wd = dt.month, dt.day, dt.weekday()

    # Black Friday — última sexta de novembro
    if m == 11 and wd == 4 and d >= 22 and (dt + timedelta(days=7)).month == 12:
        return 5.0 + rng.uniform(-0.3, 0.3)
    # Semana Black Friday
    if m == 11 and d >= 22:
        return 2.8 + rng.uniform(-0.2, 0.2)

    # Natal (15-24/12) e pós-natal (25-31/12)
    if m == 12 and 15 <= d <= 24:
        return 2.5 + rng.uniform(-0.2, 0.2)
    if m == 12 and d >= 25:
        return 1.3 + rng.uniform(-0.1, 0.1)

    # Dia das Mães — 2ª domingo de maio
    if m == 5:
        first_sun = (6 - date(dt.year, 5, 1).weekday()) % 7 + 1
        maes = first_sun + 7
        if d == maes:
            return 2.5 + rng.uniform(-0.2, 0.2)
        if maes - 5 <= d < maes:
            return 1.8 + rng.uniform(-0.1, 0.1)

    # Volta às aulas
    if m in (1, 2):
        return 1.5 + rng.uniform(-0.1, 0.1)

    # Dia das Crianças
    if m == 10 and 8 <= d <= 12:
        return 1.8 + rng.uniform(-0.1, 0.1)

    # Dia dos Pais — 2ª domingo de agosto
    if m == 8:
        first_sun = (6 - date(dt.year, 8, 1).weekday()) % 7 + 1
        pais = first_sun + 7
        if d == pais:
            return 1.8 + rng.uniform(-0.1, 0.1)

    # Dia dos Namorados (Jun 12)
    if m == 6 and 8 <= d <= 12:
        return 1.5 + rng.uniform(-0.1, 0.1)

    # Dias úteis vs fim de semana
    base = 0.8 if wd >= 5 else 1.0
    return base * (0.9 + rng.uniform(0, 0.2))


# ─────────────────────────────────────────────────────────────────────────────
# Geração de dados mestres
# ─────────────────────────────────────────────────────────────────────────────

def setup_database(conn) -> None:
    log.info("Criando schemas e tabelas...")
    with conn.cursor() as cur:
        for stmt in DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
    conn.commit()
    log.info("DDL aplicado com sucesso.")


def gen_lojas(conn) -> dict[str, int]:
    """Insere lojas e retorna mapeamento codigo→id_loja."""
    now = datetime.now(timezone.utc)
    rows = []
    for loja in LOJAS:
        rows.append({
            "codigo": loja["codigo"], "nome_loja": loja["nome_loja"], "tipo_loja": loja["tipo_loja"],
            "regiao": loja["regiao"], "cidade": loja["cidade"], "uf": loja["uf"],
            "gerente": loja["gerente"], "capacidade_m2": loja["capacidade_m2"],
            "dt_abertura": loja["dt_abertura"], "ativo": True,
            "created_at": now, "updated_at": now,
        })
    with conn.cursor() as cur:
        bulk_insert(cur, "rh.lojas", rows, "ON CONFLICT (codigo) DO NOTHING")
        cur.execute("SELECT codigo, id_loja FROM rh.lojas")
        result = {r[0]: r[1] for r in cur.fetchall()}
    conn.commit()
    log.info(f"Lojas: {len(result)} registros")
    return result


def gen_categorias(conn) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = [{"nome": c["nome"], "subcategoria": c["subcategoria"], "updated_at": now} for c in CATEGORIAS]
    with conn.cursor() as cur:
        bulk_insert(cur, "produtos.categorias", rows, "ON CONFLICT (nome) DO NOTHING")
        cur.execute("SELECT nome, id_categoria FROM produtos.categorias")
        result = {r[0]: r[1] for r in cur.fetchall()}
    conn.commit()
    log.info(f"Categorias: {len(result)} registros")
    return result


def gen_fornecedores(conn) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = [{**f, "ativo": True, "updated_at": now} for f in FORNECEDORES]
    with conn.cursor() as cur:
        bulk_insert(cur, "produtos.fornecedores", rows, "ON CONFLICT (nome_fornecedor) DO NOTHING")
        cur.execute("SELECT nome_fornecedor, id_fornecedor FROM produtos.fornecedores")
        result = {r[0]: r[1] for r in cur.fetchall()}
    conn.commit()
    log.info(f"Fornecedores: {len(result)} registros")
    return result


def gen_transportadoras(conn) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = [{**t, "ativo": True, "updated_at": now} for t in TRANSPORTADORAS]
    with conn.cursor() as cur:
        bulk_insert(cur, "logistica.transportadoras", rows, "ON CONFLICT (nome) DO NOTHING")
        cur.execute("SELECT nome, id_transportadora FROM logistica.transportadoras")
        trans_ids = {r[0]: r[1] for r in cur.fetchall()}
    conn.commit()
    log.info(f"Transportadoras: {len(trans_ids)} registros")
    return trans_ids


def gen_modalidades(conn, trans_ids: dict[str, int]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    rows = []
    for codigo, nome, trans, prazo, frete, tipo in MODALIDADES:
        rows.append({
            "id_transportadora": trans_ids[trans], "nome": nome, "codigo": codigo,
            "prazo_dias": prazo, "frete_base": frete, "tipo": tipo, "updated_at": now,
        })
    with conn.cursor() as cur:
        bulk_insert(cur, "logistica.modalidades", rows, "ON CONFLICT (codigo) DO NOTHING")
        cur.execute("SELECT codigo, id_modalidade, id_transportadora, prazo_dias, frete_base FROM logistica.modalidades")
        result = {r[0]: {"id": r[1], "id_trans": r[2], "prazo": r[3], "frete": float(r[4])} for r in cur.fetchall()}
    conn.commit()
    log.info(f"Modalidades: {len(result)} registros")
    return result


def gen_produtos(
    conn,
    cat_ids: dict[str, int],
    forn_ids: dict[str, int],
    rng: random.Random,
    start_date: date,
) -> list[dict]:
    """Gera produtos e tabela de preços. Retorna lista de dicts com info de produto."""
    now = datetime.now(timezone.utc)
    # Mapeia fornecedor por marca/categoria principal
    forn_by_cat: dict[str, list[str]] = {}
    for f in FORNECEDORES:
        forn_by_cat.setdefault(f["categoria_principal"], []).append(f["nome_fornecedor"])

    prod_rows = []
    for i, (nome, marca, cat, _, _, _, _, peso) in enumerate(PRODUTOS_CATALOG, start=1):
        sku = f"SKU{i:05d}"
        fornecedores_cat = forn_by_cat.get(cat, list(forn_ids.keys()))
        id_forn = forn_ids[rng.choice(fornecedores_cat)]
        prod_rows.append({
            "id_categoria": cat_ids[cat], "id_fornecedor": id_forn,
            "sku": sku, "nome": nome, "marca": marca, "peso_kg": peso,
            "ativo": True, "created_at": now, "updated_at": now,
        })

    with conn.cursor() as cur:
        bulk_insert(cur, "produtos.produtos", prod_rows, "ON CONFLICT (sku) DO NOTHING")
        cur.execute("SELECT id_produto, sku FROM produtos.produtos ORDER BY id_produto")
        db_prods = {r[1]: r[0] for r in cur.fetchall()}

        preco_rows = []
        for i, (nome, marca, cat, custo_min, custo_max, mg_min, mg_max, _) in enumerate(PRODUTOS_CATALOG, start=1):
            sku = f"SKU{i:05d}"
            id_prod = db_prods.get(sku)
            if not id_prod:
                continue
            custo = round2(rng.uniform(custo_min, custo_max))
            margem = rng.uniform(mg_min, mg_max)
            preco = round2(custo * (1 + margem))
            preco_rows.append({
                "id_produto": id_prod, "preco_venda": preco, "custo_unitario": custo,
                "dt_vigencia_inicio": start_date, "dt_vigencia_fim": None, "updated_at": now,
            })
        bulk_insert(cur, "produtos.precos", preco_rows,
                    "ON CONFLICT (id_produto, dt_vigencia_inicio) DO NOTHING")

        cur.execute("""
            SELECT p.id_produto, p.sku, pr.preco_venda, pr.custo_unitario
            FROM produtos.produtos p
            JOIN produtos.precos pr ON pr.id_produto = p.id_produto
        """)
        produtos_info = [
            {"id": r[0], "sku": r[1], "preco": float(r[2]), "custo": float(r[3])}
            for r in cur.fetchall()
        ]
    conn.commit()
    log.info(f"Produtos: {len(produtos_info)} SKUs com preços")
    return produtos_info


def gen_clientes(conn, rng: random.Random, n: int, start_date: date, end_date: date) -> list[int]:
    """Gera n clientes com cadastro distribuído ao longo do período. Retorna lista de IDs."""
    log.info(f"Gerando {n:,} clientes...")
    total_days = (end_date - start_date).days
    canais_origem = ["site_proprio", "loja_fisica", "marketplace_ml", "indicacao", "redes_sociais"]
    cpfs_usados: set[str] = set()
    emails_usados: set[str] = set()

    batch: list[dict] = []
    ids_inserted: list[int] = []

    with conn.cursor() as cur:
        for i in tqdm(range(n), desc="Clientes", unit="reg"):
            # garante unicidade de CPF e email
            for _ in range(10):
                cpf = fake.cpf()
                if cpf not in cpfs_usados:
                    cpfs_usados.add(cpf)
                    break
            email = f"cliente{i+1}_{rng.randint(100,999)}@{rng.choice(['gmail.com','yahoo.com.br','hotmail.com','outlook.com'])}"
            if email in emails_usados:
                email = f"c{i+1}x{rng.randint(1000,9999)}@gmail.com"
            emails_usados.add(email)

            nome = fake.name()
            primeiro = nome.split()[0]
            dias_desde_inicio = int(rng.betavariate(1.5, 2.0) * total_days)
            dt_cad = start_date + timedelta(days=dias_desde_inicio)
            uf = rng.choices(ESTADOS_BR, weights=ESTADOS_PESOS, k=1)[0]
            ts = datetime(dt_cad.year, dt_cad.month, dt_cad.day,
                          rng.randint(8, 22), rng.randint(0, 59), tzinfo=timezone.utc)
            batch.append({
                "cpf": cpf, "email": email, "telefone": fake.phone_number(),
                "primeiro_nome": primeiro, "nome_completo": nome,
                "cep": fake.postcode(), "cidade": fake.city(), "uf": uf,
                "data_cadastro": dt_cad, "canal_origem": rng.choice(canais_origem),
                "nivel_fidelidade": "Bronze", "ativo": True, "created_at": ts, "updated_at": ts,
            })

            if len(batch) >= 500:
                bulk_insert(cur, "clientes.clientes", batch, "ON CONFLICT (cpf) DO NOTHING")
                conn.commit()
                batch = []

        if batch:
            bulk_insert(cur, "clientes.clientes", batch, "ON CONFLICT (cpf) DO NOTHING")
            conn.commit()

        cur.execute("SELECT id_cliente FROM clientes.clientes ORDER BY id_cliente")
        ids_inserted = [r[0] for r in cur.fetchall()]

    # Endereços (1 por cliente)
    log.info("Gerando endereços...")
    end_batch: list[dict] = []
    with conn.cursor() as cur:
        for cid in tqdm(ids_inserted, desc="Endereços", unit="reg"):
            ts = datetime.now(timezone.utc)
            end_batch.append({
                "id_cliente": cid, "logradouro": fake.street_name(),
                "numero": str(rng.randint(1, 9999)), "complemento": rng.choice([None, "Apto " + str(rng.randint(1, 200)), None]),
                "bairro": fake.bairro() if hasattr(fake, "bairro") else "Centro",
                "cep": fake.postcode(), "cidade": fake.city(), "uf": rng.choices(ESTADOS_BR, weights=ESTADOS_PESOS, k=1)[0],
                "tipo": "principal", "created_at": ts, "updated_at": ts,
            })
            if len(end_batch) >= 500:
                bulk_insert(cur, "clientes.enderecos", end_batch, "ON CONFLICT DO NOTHING")
                conn.commit()
                end_batch = []
        if end_batch:
            bulk_insert(cur, "clientes.enderecos", end_batch, "ON CONFLICT DO NOTHING")
            conn.commit()

    # Techpoints (1 por cliente, zerado)
    log.info("Gerando techpoints...")
    tp_batch: list[dict] = []
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        for cid in ids_inserted:
            tp_batch.append({
                "id_cliente": cid, "pontos_acumulados": 0, "pontos_resgatados": 0,
                "saldo_pontos": 0, "nivel_fidelidade": "Bronze", "updated_at": now,
            })
            if len(tp_batch) >= 500:
                bulk_insert(cur, "clientes.techpoints", tp_batch, "ON CONFLICT (id_cliente) DO NOTHING")
                conn.commit()
                tp_batch = []
        if tp_batch:
            bulk_insert(cur, "clientes.techpoints", tp_batch, "ON CONFLICT (id_cliente) DO NOTHING")
            conn.commit()

    log.info(f"Clientes: {len(ids_inserted):,} registros (+ endereços + techpoints)")
    return ids_inserted


def gen_vendedores(conn, loja_ids: dict[str, int], rng: random.Random, start_date: date) -> dict[int, list[int]]:
    """Gera ~4-6 vendedores por loja física. Retorna mapa id_loja→lista de id_vendedor."""
    now = datetime.now(timezone.utc)
    lojas_fisicas = {k: v for k, v in loja_ids.items() if k not in ("ECOM", "CD01")}
    rows: list[dict] = []
    cpfs_usados: set[str] = set()

    for _, id_loja in lojas_fisicas.items():
        n_vend = rng.randint(4, 7)
        for j in range(n_vend):
            for _ in range(10):
                cpf = fake.cpf()
                if cpf not in cpfs_usados:
                    cpfs_usados.add(cpf)
                    break
            cargo = "gerente" if j == 0 else rng.choice(["vendedor", "vendedor", "vendedor", "supervisor"])
            admissao = start_date - timedelta(days=rng.randint(30, 365 * 5))
            rows.append({
                "id_loja": id_loja, "nome": fake.name(), "cpf": cpf,
                "email": f"vend{id_loja}_{j}@jstechstore.com.br", "cargo": cargo,
                "data_admissao": admissao, "ativo": True, "created_at": now, "updated_at": now,
            })

    with conn.cursor() as cur:
        bulk_insert(cur, "rh.vendedores", rows, "ON CONFLICT (cpf) DO NOTHING")
        cur.execute("SELECT id_vendedor, id_loja FROM rh.vendedores")
        vend_by_loja: dict[int, list[int]] = {}
        for vid, lid in cur.fetchall():
            vend_by_loja.setdefault(lid, []).append(vid)
    conn.commit()
    log.info(f"Vendedores: {len(rows)} registros")
    return vend_by_loja


def gen_campanhas(conn, start_date: date, end_date: date) -> list[dict]:
    """Gera campanhas de marketing para o período."""
    now = datetime.now(timezone.utc)
    campanhas_def = []

    for year in range(start_date.year, end_date.year + 1):
        campanhas_def += [
            {"nome": f"Black Friday {year}", "tipo": "black_friday", "canal": "email",
             "dt_inicio": date(year, 11, 1), "dt_fim": date(year, 11, 30),
             "orcamento": 180000.0, "objetivo": "conversao"},
            {"nome": f"Natal e Ano Novo {year}", "tipo": "natal", "canal": "social",
             "dt_inicio": date(year, 12, 1), "dt_fim": date(year, 12, 31),
             "orcamento": 120000.0, "objetivo": "conversao"},
            {"nome": f"Volta às Aulas {year}", "tipo": "volta_aulas", "canal": "search",
             "dt_inicio": date(year, 1, 1), "dt_fim": date(year, 2, 28),
             "orcamento": 80000.0, "objetivo": "conversao"},
            {"nome": f"Dia das Mães {year}", "tipo": "dia_maes", "canal": "email",
             "dt_inicio": date(year, 4, 15), "dt_fim": date(year, 5, 12),
             "orcamento": 60000.0, "objetivo": "conversao"},
            {"nome": f"Dia dos Pais {year}", "tipo": "dia_pais", "canal": "display",
             "dt_inicio": date(year, 7, 15), "dt_fim": date(year, 8, 11),
             "orcamento": 50000.0, "objetivo": "conversao"},
            {"nome": f"Dia dos Namorados {year}", "tipo": "dia_namorados", "canal": "social",
             "dt_inicio": date(year, 5, 25), "dt_fim": date(year, 6, 12),
             "orcamento": 40000.0, "objetivo": "branding"},
            {"nome": f"Liquidação de Inverno {year}", "tipo": "liquidacao", "canal": "email",
             "dt_inicio": date(year, 7, 1), "dt_fim": date(year, 7, 31),
             "orcamento": 35000.0, "objetivo": "conversao"},
            {"nome": f"Dia das Crianças {year}", "tipo": "dia_criancas", "canal": "social",
             "dt_inicio": date(year, 9, 25), "dt_fim": date(year, 10, 12),
             "orcamento": 55000.0, "objetivo": "conversao"},
        ]

    # filtra campanhas dentro do período gerado
    campanhas_def = [
        c for c in campanhas_def
        if c["dt_fim"] >= start_date and c["dt_inicio"] <= end_date
    ]

    rows = [{**c, "ativo": True, "updated_at": now} for c in campanhas_def]
    with conn.cursor() as cur:
        bulk_insert(cur, "marketing.campanhas", rows, "ON CONFLICT DO NOTHING")
        cur.execute("SELECT id_campanha, dt_inicio, dt_fim, tipo FROM marketing.campanhas")
        result = [{"id": r[0], "dt_inicio": r[1], "dt_fim": r[2], "tipo": r[3]} for r in cur.fetchall()]
    conn.commit()
    log.info(f"Campanhas: {len(result)} registros")
    return result


def gen_saldo_estoque_inicial(conn, prod_ids: list[int], loja_ids: dict[str, int],
                               rng: random.Random, ref_date: date) -> None:
    """Cria saldo de estoque inicial para todos produtos × lojas ativas."""
    now = datetime.now(timezone.utc)
    lojas_com_estoque = [v for k, v in loja_ids.items() if k != "ECOM"]
    rows = []
    for id_prod in prod_ids:
        for id_loja in lojas_com_estoque:
            rows.append({
                "id_produto": id_prod, "id_loja": id_loja,
                "qtd_disponivel": rng.randint(5, 100), "qtd_reservada": 0,
                "qtd_minima": 5, "dt_ultima_atualizacao": ref_date, "updated_at": now,
            })
    with conn.cursor() as cur:
        for i in range(0, len(rows), 500):
            bulk_insert(cur, "estoque.saldo_estoque", rows[i:i+500],
                        "ON CONFLICT (id_produto, id_loja) DO NOTHING")
        conn.commit()
    log.info(f"Saldo estoque inicial: {len(rows):,} registros")


def gen_orcamentos(conn, loja_ids: dict[str, int], start_date: date, end_date: date) -> None:
    """Gera orçamentos mensais por loja × canal para o período."""
    now = datetime.now(timezone.utc)
    lojas_fisicas = [v for k, v in loja_ids.items() if k not in ("CD01",)]
    canais_orc = ["loja_fisica", "site_proprio", "marketplace_ml", "marketplace_amazon", "marketplace_shopee"]
    rows = []
    cur_month = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    while cur_month <= end_month:
        for id_loja in lojas_fisicas:
            for canal in canais_orc:
                # e-commerce canais apenas para loja ECOM
                if canal != "loja_fisica" and id_loja != loja_ids.get("ECOM"):
                    if canal == "site_proprio" and id_loja in [loja_ids.get("ECOM")]:
                        pass
                meta_receita = round2(random.uniform(80000, 350000))
                rows.append({
                    "id_loja": id_loja, "canal_venda": canal,
                    "ano": cur_month.year, "mes": cur_month.month,
                    "valor_meta_receita": meta_receita,
                    "valor_meta_margem": round2(meta_receita * random.uniform(0.20, 0.30)),
                    "qtd_meta_pedidos": random.randint(200, 1500),
                    "updated_at": now,
                })
        # avança mês
        if cur_month.month == 12:
            cur_month = date(cur_month.year + 1, 1, 1)
        else:
            cur_month = date(cur_month.year, cur_month.month + 1, 1)

    with conn.cursor() as cur:
        for i in range(0, len(rows), 500):
            bulk_insert(cur, "financeiro.orcamentos", rows[i:i+500], "ON CONFLICT DO NOTHING")
    conn.commit()
    log.info(f"Orçamentos: {len(rows):,} registros")


# ─────────────────────────────────────────────────────────────────────────────
# Geração diária
# ─────────────────────────────────────────────────────────────────────────────

def gen_daily(
    conn,
    dt: date,
    ctx: dict,
    rng: random.Random,
) -> None:
    """Gera todos os dados transacionais para um dia."""
    produtos = ctx["produtos"]
    cliente_ids = ctx["cliente_ids"]
    loja_ids = ctx["loja_ids"]
    vend_by_loja = ctx["vend_by_loja"]
    campanhas = ctx["campanhas"]
    modalidades = ctx["modalidades"]
    # Lojas físicas (sem CD e ECOM como origem de venda)
    lojas_fisicas_ids = [v for k, v in loja_ids.items() if k not in ("ECOM", "CD01")]
    id_loja_ecom = loja_ids.get("ECOM")
    id_loja_cd = loja_ids.get("CD01")

    # Campanhas ativas hoje
    campanhas_ativas = [c for c in campanhas if c["dt_inicio"] <= dt <= c["dt_fim"]]
    id_campanha_ativa = campanhas_ativas[0]["id"] if campanhas_ativas else None

    # Número de pedidos
    base_orders = 2000
    fator = seasonality_factor(dt, rng)
    n_orders = max(50, int(base_orders * fator))

    pedidos, itens_ped, entregas_rows = [], [], []
    lancamentos, contas_rec = [], []
    movs, sessoes_rows = [], []
    comissoes_rows: list[dict] = []

    now_dt = rand_ts(dt, rng)

    for _ in range(n_orders):
        canal = rng.choices(CANAIS, weights=CANAIS_PESOS, k=1)[0]
        is_online = canal != "loja_fisica"

        if is_online:
            id_loja = id_loja_ecom
        else:
            id_loja = rng.choice(lojas_fisicas_ids)

        id_cliente = rng.choice(cliente_ids)
        dt_ped = rand_ts(dt, rng)

        # Status
        rand_status = rng.random()
        if rand_status < 0.03:
            status = "cancelado"
        elif rand_status < 0.05:
            status = "devolvido"
        else:
            status = "entregue" if (date.today() - dt).days > 7 else rng.choice(["confirmado", "enviado", "entregue"])

        # Produtos do pedido
        n_itens = rng.choices([1, 2, 3, 4, 5, 6], weights=[30, 28, 20, 12, 7, 3], k=1)[0]
        prods_escolhidos = rng.sample(produtos, min(n_itens, len(produtos)))

        valor_bruto = 0.0
        valor_desconto = 0.0
        itens_temp = []
        for prod in prods_escolhidos:
            qtd = rng.choices([1, 2, 3], weights=[70, 20, 10], k=1)[0]
            preco = prod["preco"] * (1 + rng.uniform(-0.05, 0.05))  # variação de preço ±5%
            custo = prod["custo"]
            desc_pct = rng.uniform(0, 0.15) if canal.startswith("marketplace") else rng.uniform(0, 0.08)
            desconto = round2(preco * qtd * desc_pct)
            liq_item = round2(preco * qtd - desconto)
            valor_bruto += round2(preco * qtd)
            valor_desconto += desconto
            itens_temp.append({
                "id_produto": prod["id"], "qtd_vendida": qtd,
                "preco_unitario": round2(preco), "custo_unitario": round2(custo),
                "desconto_item": desconto, "valor_liquido_item": liq_item,
                "updated_at": dt_ped,
            })

        frete = 0.0 if not is_online or rng.random() < 0.3 else round2(rng.uniform(8, 35))
        valor_liquido = round2(valor_bruto - valor_desconto + frete)
        parcelas = rng.choices([1, 2, 3, 6, 10, 12], weights=[35, 15, 15, 15, 10, 10], k=1)[0]
        metodo_pag = rng.choice(METODOS_PAGAMENTO)

        pedido = {
            "id_cliente": id_cliente, "id_loja": id_loja, "canal_venda": canal, "status": status,
            "dt_pedido": dt_ped, "dt_confirmacao": dt_ped if status != "cancelado" else None,
            "dt_cancelamento": dt_ped if status == "cancelado" else None,
            "valor_bruto": round2(valor_bruto), "valor_desconto": round2(valor_desconto),
            "valor_frete": frete, "valor_liquido": valor_liquido,
            "parcelas": parcelas, "metodo_pagamento": metodo_pag,
            "cupom": f"CUPOM{rng.randint(100,999)}" if rng.random() < 0.1 else None,
            "id_campanha": id_campanha_ativa if rng.random() < 0.3 else None,
            "created_at": dt_ped, "updated_at": dt_ped,
        }
        pedidos.append(pedido)
        pedidos[-1]["_itens"] = itens_temp  # payload temporário

    if not pedidos:
        return

    # Inserir pedidos em lote e capturar IDs
    with conn.cursor() as cur:
        ped_cols = [k for k in pedidos[0].keys() if not k.startswith("_")]
        ped_values = [[p[c] for c in ped_cols] for p in pedidos]
        execute_values(
            cur,
            f"INSERT INTO vendas.pedidos ({', '.join(ped_cols)}) VALUES %s RETURNING id_pedido",
            ped_values, page_size=500,
        )
        ped_ids = [r[0] for r in cur.fetchall()]

    # Montar itens, entregas, financeiro e analytics com IDs reais
    for pedido, id_ped in zip(pedidos, ped_ids):
        canal = pedido["canal_venda"]
        status = pedido["status"]
        id_loja = pedido["id_loja"]
        dt_ped = pedido["dt_pedido"]
        valor_liq = float(pedido["valor_liquido"])
        parcelas = pedido["parcelas"]
        itens_temp = pedido["_itens"]

        # Itens do pedido
        for it in itens_temp:
            itens_ped.append({**it, "id_pedido": id_ped})

        # Entrega (apenas pedidos não cancelados de canal online ou marketplace)
        if status not in ("cancelado",) and canal != "loja_fisica":
            modal_key = rng.choice(["SEDEX", "PAC", "JADLOG_E", "JADLOG_E2", "ML_ENV"])
            if canal.startswith("marketplace_ml"):
                modal_key = "ML_ENV"
            modal = modalidades[modal_key]
            prazo_dias = modal["prazo"] + rng.randint(-1, 2)
            dt_post = dt + timedelta(days=1)
            dt_prom = dt_post + timedelta(days=prazo_dias)
            entregue = status == "entregue"
            dt_ef = dt_prom + timedelta(days=rng.randint(-1, 3)) if entregue else None
            sla = (dt_ef <= dt_prom) if dt_ef else None
            entregas_rows.append({
                "id_pedido": id_ped, "id_transportadora": modal["id_trans"],
                "id_modalidade": modal["id"], "id_loja_origem": id_loja_ecom or id_loja,
                "codigo_rastreio": f"BR{rng.randint(100000000, 999999999)}BR" if modal_key != "RETIRADA" else None,
                "dt_postagem": dt_post, "dt_promessa": dt_prom, "dt_efetiva": dt_ef,
                "fl_sla_atendido": sla, "status": "entregue" if entregue else "em_transito",
                "updated_at": dt_ped,
            })

        # Movimentação de estoque (saída)
        if status not in ("cancelado",):
            id_loja_estoque = id_loja if id_loja != id_loja_ecom else id_loja_cd
            for it in itens_temp:
                movs.append({
                    "id_produto": it["id_produto"], "id_loja": id_loja_estoque,
                    "tipo_mov": "saida", "qtd": -it["qtd_vendida"],
                    "dt_movimentacao": dt_ped, "id_pedido": id_ped,
                    "custo_unitario": it["custo_unitario"], "observacao": f"Venda pedido #{id_ped}",
                    "updated_at": dt_ped,
                })

        # Financeiro — lançamento receita
        if status not in ("cancelado",):
            lancamentos.append({
                "id_pedido": id_ped, "id_loja": id_loja,
                "tipo": "receita", "valor": valor_liq,
                "dt_lancamento": dt, "dt_competencia": dt,
                "descricao": f"Venda pedido #{id_ped} via {canal}",
                "updated_at": dt_ped,
            })
            # Contas a receber
            dt_venc = dt + timedelta(days=rng.randint(1, parcelas * 30))
            dt_pag = dt_venc - timedelta(days=rng.randint(0, 3)) if status == "entregue" else None
            contas_rec.append({
                "id_pedido": id_ped, "valor_original": valor_liq, "valor_pago": valor_liq if dt_pag else 0,
                "dt_vencimento": dt_venc, "dt_pagamento": dt_pag,
                "status": "pago" if dt_pag else "pendente", "updated_at": dt_ped,
            })

        # Comissão (apenas loja física)
        if canal == "loja_fisica" and status not in ("cancelado",):
            vendedores_loja = vend_by_loja.get(id_loja, [])
            if vendedores_loja:
                id_vend = rng.choice(vendedores_loja)
                pct = rng.uniform(0.012, 0.025)
                comissoes_rows.append({
                    "id_vendedor": id_vend, "id_pedido": id_ped,
                    "valor_venda": valor_liq, "percentual_comissao": round2(pct),
                    "valor_comissao": round2(valor_liq * pct),
                    "dt_competencia": dt, "status": "pendente", "updated_at": dt_ped,
                })

        # Web analytics — sessão + eventos (apenas canais digitais)
        if canal != "loja_fisica":
            dt_ini = dt_ped - timedelta(minutes=rng.randint(5, 40))
            dt_fim_sess = dt_ped + timedelta(minutes=rng.randint(1, 15))
            id_cliente = pedido["id_cliente"]
            canal_ori = canal if "marketplace" not in canal else "marketplace"
            sessoes_rows.append({
                "id_cliente": id_cliente, "canal_origem": canal_ori,
                "device_type": rng.choice(["desktop", "mobile", "mobile", "tablet"]),
                "dt_inicio": dt_ini, "dt_fim": dt_fim_sess,
                "paginas_visitadas": rng.randint(3, 20),
                "converteu": status not in ("cancelado",),
                "id_pedido": id_ped if status not in ("cancelado",) else None,
                "updated_at": dt_ped,
            })

    # Sessões de navegação sem conversão (~8× pedidos online)
    n_online_orders = sum(1 for p in pedidos if p["canal_venda"] != "loja_fisica")
    for _ in range(n_online_orders * 7):
        dt_ini = rand_ts(dt, rng)
        sessoes_rows.append({
            "id_cliente": rng.choice(cliente_ids) if rng.random() < 0.4 else None,
            "canal_origem": rng.choice(["organico", "search", "social", "email", "direto"]),
            "device_type": rng.choice(["desktop", "mobile", "mobile", "tablet"]),
            "dt_inicio": dt_ini, "dt_fim": dt_ini + timedelta(minutes=rng.randint(1, 30)),
            "paginas_visitadas": rng.randint(1, 8), "converteu": False,
            "id_pedido": None, "updated_at": dt_ini,
        })

    with conn.cursor() as cur:
        # Itens do pedido
        for i in range(0, len(itens_ped), 500):
            bulk_insert(cur, "vendas.itens_pedido", itens_ped[i:i+500])

        # Entregas
        if entregas_rows:
            bulk_insert(cur, "logistica.entregas", entregas_rows)

        # Movimentações estoque
        if movs:
            for i in range(0, len(movs), 500):
                bulk_insert(cur, "estoque.movimentacoes", movs[i:i+500])

        # Financeiro — lançamentos
        if lancamentos:
            execute_values(
                cur,
                "INSERT INTO financeiro.lancamentos (id_pedido,id_loja,tipo,valor,dt_lancamento,dt_competencia,descricao,updated_at) VALUES %s RETURNING id_lancamento",
                [[r["id_pedido"], r["id_loja"], r["tipo"], r["valor"], r["dt_lancamento"], r["dt_competencia"], r["descricao"], r["updated_at"]] for r in lancamentos],
                page_size=500,
            )
            lanc_ids = [r[0] for r in cur.fetchall()]

            parc_rows = []
            for lanc_id, lanc in zip(lanc_ids, lancamentos):
                valor_total = float(lanc["valor"])
                parcelas_n = rng.choices([1, 2, 3, 6, 10, 12], weights=[35, 15, 15, 15, 10, 10], k=1)[0]
                val_parc = round2(valor_total / parcelas_n)
                dt_lanc = lanc["dt_lancamento"]
                for n in range(1, parcelas_n + 1):
                    dt_venc = dt_lanc + timedelta(days=30 * n)
                    dt_pag = dt_venc - timedelta(days=rng.randint(0, 5)) if rng.random() < 0.75 else None
                    parc_rows.append({
                        "id_lancamento": lanc_id, "numero_parcela": n,
                        "valor_parcela": val_parc, "dt_vencimento": dt_venc,
                        "dt_pagamento": dt_pag, "status": "pago" if dt_pag else "pendente",
                        "updated_at": now_dt,
                    })
            if parc_rows:
                for i in range(0, len(parc_rows), 500):
                    bulk_insert(cur, "financeiro.parcelas", parc_rows[i:i+500])

        # Contas a receber
        if contas_rec:
            bulk_insert(cur, "financeiro.contas_receber", contas_rec)

        # Comissões
        if comissoes_rows:
            bulk_insert(cur, "rh.comissoes", comissoes_rows)

        # Sessões web
        if sessoes_rows:
            execute_values(
                cur,
                "INSERT INTO web_analytics.sessoes (id_cliente,canal_origem,device_type,dt_inicio,dt_fim,paginas_visitadas,converteu,id_pedido,updated_at) VALUES %s RETURNING id_sessao",
                [[s["id_cliente"], s["canal_origem"], s["device_type"], s["dt_inicio"], s["dt_fim"], s["paginas_visitadas"], s["converteu"], s["id_pedido"], s["updated_at"]] for s in sessoes_rows],
                page_size=500,
            )
            sessao_ids = [r[0] for r in cur.fetchall()]

            # Eventos de carrinho para sessões com conversão
            ev_rows = []
            for sid, sess in zip(sessao_ids, sessoes_rows):
                if not sess["converteu"]:
                    continue
                n_ev = rng.randint(1, 4)
                prods_ev = rng.sample(produtos, min(n_ev, len(produtos)))
                for prod in prods_ev:
                    ev_rows.append({
                        "id_sessao": sid, "id_produto": prod["id"],
                        "tipo_evento": "add_to_cart", "dt_evento": sess["dt_inicio"],
                        "qtd": 1, "preco_na_epoca": prod["preco"], "updated_at": sess["updated_at"],
                    })
                ev_rows.append({
                    "id_sessao": sid, "id_produto": rng.choice(prods_ev)["id"],
                    "tipo_evento": "purchase", "dt_evento": sess["dt_fim"],
                    "qtd": 1, "preco_na_epoca": rng.choice(prods_ev)["preco"], "updated_at": sess["updated_at"],
                })
            if ev_rows:
                for i in range(0, len(ev_rows), 500):
                    bulk_insert(cur, "web_analytics.eventos_carrinho", ev_rows[i:i+500])

        # Devoluções (~5% dos pedidos entregues com delay de 5-30 dias)
        dev_rows = []
        for pedido, id_ped in zip(pedidos, ped_ids):
            if pedido["status"] == "devolvido" and pedido["_itens"]:
                item = rng.choice(pedido["_itens"])
                dt_dev = dt + timedelta(days=rng.randint(5, 30))
                dev_rows.append({
                    "id_pedido": id_ped, "id_produto": item["id_produto"],
                    "dt_devolucao": dt_dev, "motivo": rng.choice(MOTIVOS_DEVOLUCAO),
                    "qtd_devolvida": item["qtd_vendida"],
                    "valor_devolvido": item["valor_liquido_item"],
                    "status": "aprovada", "updated_at": now_dt,
                })
        if dev_rows:
            bulk_insert(cur, "vendas.devolucoes", dev_rows)

        # Leads de campanha
        if campanhas_ativas:
            n_leads = rng.randint(50, 300)
            lead_rows = []
            for _ in range(n_leads):
                camp = rng.choice(campanhas_ativas)
                lead_rows.append({
                    "id_campanha": camp["id"],
                    "id_cliente": rng.choice(cliente_ids) if rng.random() < 0.5 else None,
                    "canal": rng.choice(["email", "social", "search", "display"]),
                    "dt_lead": dt, "convertido": rng.random() < 0.05, "updated_at": now_dt,
                })
            bulk_insert(cur, "marketing.leads", lead_rows)

        # Atribuição de campanha (30% dos pedidos com campanha ativa)
        if campanhas_ativas:
            attr_rows = []
            for pedido, id_ped in zip(pedidos, ped_ids):
                if pedido.get("id_campanha") and pedido["status"] != "cancelado":
                    attr_rows.append({
                        "id_pedido": id_ped, "id_campanha": pedido["id_campanha"],
                        "canal_atribuicao": pedido["canal_venda"],
                        "tipo_atribuicao": "last_click", "peso": 1.0, "updated_at": now_dt,
                    })
            if attr_rows:
                bulk_insert(cur, "marketing.atribuicao", attr_rows)

    conn.commit()


def gen_metas_mensais(conn, vend_by_loja: dict[int, list[int]], ano: int, mes: int) -> None:
    """Gera metas mensais para todos os vendedores."""
    now = datetime.now(timezone.utc)
    rows = []
    for vendedores in vend_by_loja.values():
        for id_vend in vendedores:
            rows.append({
                "id_vendedor": id_vend, "ano": ano, "mes": mes,
                "meta_valor": round2(random.uniform(40000, 120000)),
                "meta_qtd_pedidos": random.randint(80, 300),
                "updated_at": now,
            })
    with conn.cursor() as cur:
        bulk_insert(cur, "rh.metas", rows, "ON CONFLICT DO NOTHING")
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint principal
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gerador de dados históricos JSTechStore → Supabase")
    p.add_argument("--start-date", required=True, help="Data inicial YYYY-MM-DD")
    p.add_argument("--end-date",   required=True, help="Data final YYYY-MM-DD")
    p.add_argument("--seed", type=int, default=42, help="Semente para reprodutibilidade (default: 42)")
    p.add_argument("--n-clientes", type=int, default=100_000, help="Número de clientes a gerar (default: 100000)")
    p.add_argument("--skip-ddl", action="store_true", help="Não reexecutar o DDL (tabelas já criadas)")
    p.add_argument("--force", action="store_true", help="Trunca dados transacionais antes de gerar (re-geração)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date   = date.fromisoformat(args.end_date)

    rng = random.Random(args.seed)
    Faker.seed(args.seed)
    random.seed(args.seed)

    log.info(f"Iniciando geração: {start_date} → {end_date} | seed={args.seed} | clientes={args.n_clientes:,}")

    conn = connect()
    try:
        if not args.skip_ddl:
            setup_database(conn)

        if args.force:
            log.warning("--force: truncando tabelas transacionais...")
            with conn.cursor() as cur:
                cur.execute("""
                    TRUNCATE TABLE
                        web_analytics.eventos_carrinho, web_analytics.sessoes,
                        rh.comissoes, rh.metas,
                        marketing.atribuicao, marketing.leads,
                        financeiro.parcelas, financeiro.contas_receber,
                        financeiro.lancamentos, financeiro.orcamentos,
                        estoque.movimentacoes, estoque.saldo_estoque,
                        logistica.entregas,
                        vendas.devolucoes, vendas.itens_pedido, vendas.pedidos,
                        clientes.techpoints, clientes.enderecos, clientes.clientes,
                        rh.vendedores,
                        produtos.precos, produtos.produtos,
                        logistica.modalidades, logistica.transportadoras,
                        marketing.campanhas,
                        rh.lojas, produtos.categorias, produtos.fornecedores
                    CASCADE
                """)
            conn.commit()
            log.info("Truncate concluído.")

        # Dados mestres
        loja_ids   = gen_lojas(conn)
        cat_ids    = gen_categorias(conn)
        forn_ids   = gen_fornecedores(conn)
        trans_ids  = gen_transportadoras(conn)
        modalidades = gen_modalidades(conn, trans_ids)
        produtos   = gen_produtos(conn, cat_ids, forn_ids, rng, start_date)
        campanhas  = gen_campanhas(conn, start_date, end_date)
        cliente_ids = gen_clientes(conn, rng, args.n_clientes, start_date, end_date)
        vend_by_loja = gen_vendedores(conn, loja_ids, rng, start_date)
        gen_saldo_estoque_inicial(conn, [p["id"] for p in produtos], loja_ids, rng, start_date)
        gen_orcamentos(conn, loja_ids, start_date, end_date)

        ctx = {
            "produtos": produtos,
            "cliente_ids": cliente_ids,
            "loja_ids": loja_ids,
            "vend_by_loja": vend_by_loja,
            "campanhas": campanhas,
            "modalidades": modalidades,
        }

        # Loop diário
        total_days = (end_date - start_date).days + 1
        log.info(f"Iniciando geração de {total_days} dias de dados transacionais...")
        current_month = (start_date.year, start_date.month)

        for n in tqdm(range(total_days), desc="Dias", unit="dia"):
            dt = start_date + timedelta(days=n)

            # Metas mensais no 1º dia do mês
            if (dt.year, dt.month) != current_month or n == 0:
                current_month = (dt.year, dt.month)
                gen_metas_mensais(conn, vend_by_loja, dt.year, dt.month)

            gen_daily(conn, dt, ctx, rng)

    except Exception:
        log.exception("Erro fatal durante geração de dados.")
        return 1
    finally:
        conn.close()

    log.info("=== Geração concluída com sucesso! ===")
    log.info("Próximo passo: python -m ingestion.connectors.postgres.extract --mode full")
    return 0


if __name__ == "__main__":
    sys.exit(main())
