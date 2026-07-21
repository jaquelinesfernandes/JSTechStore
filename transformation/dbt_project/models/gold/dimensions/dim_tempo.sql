{{ config(materialized='table') }}

/*
  Dimensão tempo: spine diária de {{ var("dim_inicio") }} a {{ var("dim_fim") }}.
  Inclui atributos de calendário, sazonalidade e feriados nacionais.
*/

WITH spine AS (
    SELECT UNNEST(
        GENERATE_SERIES(
            DATE '{{ var("dim_inicio") }}',
            DATE '{{ var("dim_fim") }}',
            INTERVAL '1 day'
        )
    )::DATE AS data_full
),
feriados AS (
    SELECT data FROM {{ ref('feriados_nacionais') }}
)
SELECT
    -- Surrogate key: YYYYMMDD como integer
    CAST(STRFTIME(data_full, '%Y%m%d') AS INTEGER)    AS sk_tempo,
    data_full,

    -- Granularidades
    EXTRACT(YEAR  FROM data_full)::INTEGER             AS ano,
    EXTRACT(MONTH FROM data_full)::INTEGER             AS mes,
    EXTRACT(DAY   FROM data_full)::INTEGER             AS dia,
    EXTRACT(QUARTER FROM data_full)::INTEGER           AS trimestre,
    EXTRACT(WEEK  FROM data_full)::INTEGER             AS semana_iso,
    EXTRACT(DOW   FROM data_full)::INTEGER             AS dia_semana_num,   -- 0=Dom 6=Sab

    -- Labels
    CASE EXTRACT(MONTH FROM data_full)
        WHEN 1  THEN 'Janeiro'   WHEN 2  THEN 'Fevereiro' WHEN 3  THEN 'Março'
        WHEN 4  THEN 'Abril'     WHEN 5  THEN 'Maio'      WHEN 6  THEN 'Junho'
        WHEN 7  THEN 'Julho'     WHEN 8  THEN 'Agosto'    WHEN 9  THEN 'Setembro'
        WHEN 10 THEN 'Outubro'   WHEN 11 THEN 'Novembro'  WHEN 12 THEN 'Dezembro'
    END                                                AS nome_mes,

    CASE EXTRACT(DOW FROM data_full)
        WHEN 0 THEN 'Domingo'    WHEN 1 THEN 'Segunda-feira' WHEN 2 THEN 'Terça-feira'
        WHEN 3 THEN 'Quarta-feira' WHEN 4 THEN 'Quinta-feira' WHEN 5 THEN 'Sexta-feira'
        WHEN 6 THEN 'Sábado'
    END                                                AS nome_dia_semana,

    CASE EXTRACT(QUARTER FROM data_full)
        WHEN 1 THEN 'Q1' WHEN 2 THEN 'Q2' WHEN 3 THEN 'Q3' WHEN 4 THEN 'Q4'
    END                                                AS nome_trimestre,

    -- Flags
    EXTRACT(DOW FROM data_full) IN (0, 6)             AS fl_fim_de_semana,
    (f.data IS NOT NULL)                              AS fl_feriado_nacional,

    -- Períodos comerciais
    CASE
        WHEN EXTRACT(MONTH FROM data_full) = 11
             AND EXTRACT(DOW  FROM data_full) = 5
             AND EXTRACT(DAY  FROM data_full) >= 22
             AND EXTRACT(MONTH FROM (data_full + INTERVAL '7 days')) = 12  -- próxima 6a-feira já é dezembro
        THEN TRUE
        ELSE FALSE
    END                                                AS fl_black_friday,

    STRFTIME(data_full, '%Y-%m')                       AS ano_mes,
    STRFTIME(data_full, '%Y-Q') || CAST(EXTRACT(QUARTER FROM data_full) AS VARCHAR) AS ano_trimestre

FROM spine s
LEFT JOIN feriados f ON f.data = s.data_full
