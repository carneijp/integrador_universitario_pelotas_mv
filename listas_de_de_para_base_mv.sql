-- unidade de medida
SELECT DISTINCT CD_UNIDADE, DS_UNIDADE FROM dbamv.UNI_PRO ORDER BY CD_UNIDADE;

-- intervalo
SELECT DISTINCT cd_tip_fre, ds_tip_fre FROM dbamv.tip_fre ORDER BY DS_TIP_FRE asc;

-- unidades hospitalares
SELECT DISTINCT cd_unid_int, ds_unid_int FROM dbamv.unid_int WHERE 1=1 AND SN_ATIVO = 'S';

-- via
SELECT DISTINCT cd_for_apl, ds_for_apl FROM dbamv.FOR_APL;

-- antibiotico
SELECT DISTINCT cd_tip_presc, ds_tip_presc FROM dbamv.TIP_PRESC WHERE CD_TIP_ESQ = 'MDA' ORDER BY ds_tip_presc ASC;

-- intervalo a partir dos antibioticos já prescritos
SELECT distinct
	it.CD_TIP_FRE, tip.DS_TIP_FRE
FROM  
	dbamv.itpre_med it
	INNER JOIN dbamv.tip_fre tip ON it.CD_TIP_FRE = tip.CD_TIP_FRE
WHERE 1=1
	AND it.CD_TIP_ESQ = 'MDA';

-- unidade de medida a partir dos antibioticos já prescritos
SELECT distinct
	tip.ds_unidade--, tip.DS_UNIDADE
FROM  
	dbamv.itpre_med it
	INNER JOIN dbamv.UNI_PRO tip ON it.CD_UNI_PRO = tip.CD_UNI_PRO
WHERE 1=1
	AND it.CD_TIP_ESQ = 'MDA'
ORDER BY ds_unidade;

-- pegar os médicos que ja tenham prescrito um antibiotico, que sejam ativos e possuam crm
SELECT DISTINCT
	p.CD_PRESTADOR, pres.NM_PRESTADOR, pres.NR_CPF_CGC, pres.NR_FONE_CONTATO, pres.DS_EMAIL, pres.DS_CODIGO_CONSELHO
FROM 
	dbamv.pre_med p
	INNER JOIN dbamv.itpre_med it ON p.CD_PRE_MED = it.CD_PRE_MED
	INNER JOIN dbamv.PRESTADOR pres ON p.CD_PRESTADOR = pres.CD_PRESTADOR 
WHERE it.CD_TIP_ESQ = 'MDA'
 	AND pres.DS_CODIGO_CONSELHO IS NOT NULL 
 	AND pres.TP_SITUACAO = 'A' -- ATIVO
 	AND pres.CD_CONSELHO = 1; -- CRM