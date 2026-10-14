DROP TABLE DBAMV.user_qualis;
DROP TRIGGER DBAMV.delete_antibiotic_qualis;
DROP TRIGGER DBAMV.update_antibiotic_qualis;
DROP TRIGGER DBAMV.copy_itpre_med_qualis;
DROP TABLE DBAMV.antibiotic_qualis;
DROP PROCEDURE DBAMV.append_to_body_sended;
DROP TRIGGER DBAMV.CAPTURE_CULTURA_TO_QUALIS;
DROP TRIGGER DBAMV.UPDATE_CULTURA_TO_QUALIS;
DROP TRIGGER DBAMV.COPY_PRESCR_MEDICA_QUALIS;
DROP TRIGGER DBAMV.UPDATE_PRESC_QUALIS;

CREATE TABLE qualis_trigger_execution (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_trigger VARCHAR2(100),
    inicio TIMESTAMP,
    fim TIMESTAMP,
    duracao_ms NUMBER,
    execution_status VARCHAR2(4000)
);
CREATE INDEX IDX_PRESCRIPTION_QUALIS_STATUS ON DBAMV.PRESCRIPTION_QUALIS(prescr_id, prescr_sended_status, prescr_status, dt_liberacao, dt_suspensao);

SELECT * FROM dbamv.qualis_trigger_execution;
SELECT * FROM dbamv.bacteriology_qualis;
SELECT * FROM dbamv.prescription_qualis;

INSERT INTO dbamv.bacteriology_qualis( cd_ped_lab, cd_exa_lab, cd_itped_lab, bacteriology_sended_status)
SELECT 
  cd_ped_lab, cd_exa_lab, cd_itped_lab, '0' 
FROM dbamv.cultura c
  WHERE cd_ped_lab|| '_' || cd_exa_lab|| '_' || cd_itped_lab NOT IN (SELECT cd_ped_lab|| '_' || cd_exa_lab|| '_' || cd_itped_lab FROM dbamv.bacteriology_qualis)
    AND c.tp_resultado = 'P';

CREATE OR REPLACE TRIGGER DBAMV.CAPTURE_CULTURA_TO_QUALIS
AFTER INSERT OR UPDATE ON DBAMV.CULTURA
FOR EACH ROW
DECLARE
  cd_multi_empresa NUMBER;
  v_inicio TIMESTAMP := SYSTIMESTAMP;
BEGIN
    IF :NEW.TP_RESULTADO = 'P' THEN

        SELECT p.cd_multi_empresa
        INTO cd_multi_empresa
        FROM dbamv.ped_lab p
        WHERE p.cd_ped_lab = :NEW.cd_ped_lab;

        IF cd_multi_empresa = 1 THEN
            MERGE INTO DBAMV.BACTERIOLOGY_QUALIS p
            USING (
                SELECT
                    :NEW.CD_PED_LAB  AS cd_ped_lab,
                    :NEW.CD_EXA_LAB  AS cd_exa_lab,
                    :NEW.CD_ITPED_LAB AS cd_itped_lab
                FROM dual
            ) s
            ON (
                p.CD_PED_LAB   = s.cd_ped_lab
                AND p.CD_EXA_LAB   = s.cd_exa_lab
                AND p.CD_ITPED_LAB = s.cd_itped_lab
            )
            WHEN MATCHED THEN
                UPDATE
                SET p.BACTERIOLOGY_SENDED_STATUS =
                        CASE
                            WHEN p.BACTERIOLOGY_SENDED_STATUS IN ('1', '-2') THEN '2'
                            ELSE '0'
                        END
                WHERE p.BACTERIOLOGY_SENDED_STATUS NOT IN ('0','2')
            WHEN NOT MATCHED THEN
                INSERT (CD_PED_LAB, CD_EXA_LAB, CD_ITPED_LAB, BACTERIOLOGY_SENDED_STATUS)
                VALUES (s.cd_ped_lab, s.cd_exa_lab, s.cd_itped_lab, '0');
        END IF;
    END IF;
    
    INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
    VALUES (
        'CAPTURE_CULTURA_TO_QUALIS',
        v_inicio,
        SYSTIMESTAMP,
        EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
        'SUCCESS'
    );
EXCEPTION
      WHEN OTHERS THEN
        INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
        VALUES (
            'CAPTURE_CULTURA_TO_QUALIS',
            v_inicio,
            SYSTIMESTAMP,
            EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
            'ERROR'
        );
END;

CREATE OR REPLACE TRIGGER DBAMV.UPDATE_CULTURA_TO_QUALIS
FOR INSERT OR UPDATE ON DBAMV.ITCULTURA
COMPOUND TRIGGER
 
    v_tab DBAMV.TYPE_QUALIS_BACT_KEY_TABLE := DBAMV.TYPE_QUALIS_BACT_KEY_TABLE();
    v_inicio TIMESTAMP;
    PROCEDURE log_execucao(p_status VARCHAR2) IS
        PRAGMA AUTONOMOUS_TRANSACTION;
    BEGIN
        INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
        VALUES (
            'UPDATE_CULTURA_TO_QUALIS',
            v_inicio,
            SYSTIMESTAMP,
            EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
            p_status
        );
        COMMIT;
    END log_execucao;
 
BEFORE STATEMENT IS
BEGIN
    v_inicio := SYSTIMESTAMP;
END BEFORE STATEMENT;

BEFORE EACH ROW IS
BEGIN
    v_tab.EXTEND;
    v_tab(v_tab.COUNT) := DBAMV.TYPE_QUALIS_BACT_KEY(
        :NEW.CD_PED_LAB,
        :NEW.CD_EXA_LAB,
        :NEW.CD_ITPED_LAB
    );
END BEFORE EACH ROW;
 
AFTER STATEMENT IS
BEGIN

    MERGE INTO DBAMV.BACTERIOLOGY_QUALIS p
    USING (
        SELECT DISTINCT x.CD_PED_LAB, x.CD_EXA_LAB, x.CD_ITPED_LAB
        FROM TABLE(v_tab) x
        INNER JOIN DBAMV.PED_LAB pl
            ON x.CD_PED_LAB = pl.CD_PED_LAB
        WHERE pl.CD_MULTI_EMPRESA = 1
    ) s
    ON (p.CD_PED_LAB = s.CD_PED_LAB
        AND p.CD_EXA_LAB = s.CD_EXA_LAB
        AND p.CD_ITPED_LAB = s.CD_ITPED_LAB)
    WHEN MATCHED THEN
        UPDATE SET p.BACTERIOLOGY_SENDED_STATUS =
                    CASE
                        WHEN p.BACTERIOLOGY_SENDED_STATUS IN ('1', '-2') THEN '2'
                        ELSE '0'
                    END
        WHERE p.BACTERIOLOGY_SENDED_STATUS NOT IN ('0', '2')
    WHEN NOT MATCHED THEN
        INSERT (CD_PED_LAB, CD_EXA_LAB, CD_ITPED_LAB, BACTERIOLOGY_SENDED_STATUS)
        VALUES (s.CD_PED_LAB, s.CD_EXA_LAB, s.CD_ITPED_LAB, '0');
 
    log_execucao('SUCCESS');
 
EXCEPTION
    WHEN OTHERS THEN
        log_execucao('ERROR');
END AFTER STATEMENT;
END UPDATE_CULTURA_TO_QUALIS;


CREATE OR REPLACE TRIGGER DBAMV.copy_prescr_medica_qualis
AFTER INSERT ON DBAMV.PRE_MED
REFERENCING NEW AS nova
FOR EACH ROW
DECLARE
  v_inicio TIMESTAMP := SYSTIMESTAMP;
BEGIN
    INSERT INTO DBAMV.prescription_qualis (
        prescr_id,
        cd_medico,
        dt_liberacao,
        nr_atendimento,
        prescr_status,
        prescr_sended_status,
        hospital_unity_id,
        infection_date,
        patient_hospital_id
    )
    SELECT
        :nova.cd_pre_med,
        :nova.cd_prestador,
        :nova.dh_impressao,
        :nova.cd_atendimento,
        '0',
        '0',
        :nova.cd_unid_int,
        SYSDATE,
        A.cd_paciente
    FROM DBAMV.ATENDIME A
    WHERE A.cd_atendimento = :nova.cd_atendimento
      AND A.cd_multi_empresa = 1;

    INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
    VALUES (
        'copy_prescr_medica_qualis',
        v_inicio,
        SYSTIMESTAMP,
        EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
        'SUCCESS'
    );
EXCEPTION
    WHEN OTHERS THEN
        INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
        VALUES (
            'copy_prescr_medica_qualis',
            v_inicio,
            SYSTIMESTAMP,
            EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
            'ERROR'
        );
END;

CREATE OR REPLACE TRIGGER dbamv.update_presc_qualis
AFTER UPDATE OF dh_impressao ON dbamv.PRE_MED
REFERENCING NEW AS nova OLD AS velha
FOR EACH ROW
DECLARE
  v_inicio TIMESTAMP := SYSTIMESTAMP;
BEGIN
    UPDATE DBAMV.prescription_qualis
    SET
      cd_medico = :nova.cd_prestador,
      dt_liberacao = :nova.dh_impressao,
      prescr_status = '0',
      prescr_sended_status = '0'
    WHERE prescr_id = :nova.cd_pre_med
        AND prescr_sended_status IS NOT NULL
        AND prescr_sended_status NOT IN ('1')
        AND EXISTS (SELECT 1 FROM DBAMV.ATENDIME A WHERE A.cd_atendimento = :nova.cd_atendimento AND A.cd_multi_empresa = 1);
    
    INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
    VALUES (
        'update_presc_qualis',
        v_inicio,
        SYSTIMESTAMP,
        EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
        'SUCCESS'
    );
EXCEPTION
    WHEN OTHERS THEN
        INSERT INTO qualis_trigger_execution (nome_trigger, inicio, fim, duracao_ms, execution_status)
        VALUES (
            'update_presc_qualis',
            v_inicio,
            SYSTIMESTAMP,
            EXTRACT(SECOND FROM (SYSTIMESTAMP - v_inicio)) * 1000,
            'ERROR'
        );
END;


SELECT * FROM dbamv.itcultura;

UPDATE dbamv.itcultura it 
SET
  nr_mic = '1'
WHERE it.cd_ped_lab = 33 AND it.cd_exa_lab = 1643 AND it.cd_itped_lab = 113 AND cd_germes = 229;

SELECT * FROM dbamv.bacteriology_qualis it WHERE it.cd_ped_lab = 33 AND it.cd_exa_lab = 1643 AND it.cd_itped_lab = 113 ; 

 UPDATE dbamv.bacteriology_qualis it 
 SET
    bacteriology_sended_status = '1'
 WHERE it.cd_ped_lab = 33 AND it.cd_exa_lab = 1643 AND it.cd_itped_lab = 113 ;

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON dbamv.prescription_qualis TO qualis;
GRANT SELECT, INSERT, UPDATE, DELETE ON dbamv.bacteriology_qualis TO qualis;
GRANT SELECT, INSERT ON DBAMV.PRE_MED TO qualis;
GRANT SELECT ON DBAMV.ITPRE_MED TO qualis;
GRANT SELECT ON DBAMV.TIP_ESQ TO qualis;
GRANT SELECT ON DBAMV.TIP_PRESC TO qualis;
GRANT SELECT ON DBAMV.ATENDIME TO qualis;
GRANT SELECT ON DBAMV.PACIENTE TO qualis;
GRANT SELECT ON DBAMV.PAGU_OBJETO TO qualis;
GRANT SELECT ON DBAMV.PRESTADOR TO qualis;
GRANT SELECT ON DBAMV.TIP_PRESTA TO qualis;
GRANT SELECT ON DBAMV.UNI_PRO TO qualis;
GRANT SELECT ON DBAMV.TIP_FRE TO qualis;
GRANT SELECT ON DBAMV.FOR_APL TO qualis;
GRANT SELECT ON DBAMV.UNID_INT TO qualis;
GRANT SELECT ON DBAMV.setor TO qualis;
GRANT SELECT ON DBAMV.CID TO qualis;
GRANT SELECT, INSERT ON DBAMV.PW_DOCUMENTO_CLINICO TO qualis;
GRANT SELECT ON DBAMV.PED_LAB TO qualis;
GRANT SELECT ON DBAMV.ITPED_LAB TO qualis;
GRANT SELECT ON DBAMV.RES_EXA TO qualis;
GRANT SELECT ON DBAMV.SUBS_PAC TO qualis;
GRANT SELECT ON DBAMV.SUBSTANCIA TO qualis;
GRANT SELECT ON DBAMV.SEQ_PW_DOCUMENTO_CLINICO TO qualis;
GRANT SELECT ON DBAMV.SEQ_PRE_MED TO qualis;
GRANT SELECT ON DBAMV.EXA_LAB TO qualis;
GRANT SELECT ON DBAMV.COLETA_SINAL_VITAL TO qualis;
GRANT SELECT ON DBAMV.ITCOLETA_SINAL_VITAL TO qualis;
GRANT SELECT ON DBAMV.GERMES TO qualis;
GRANT SELECT ON DBAMV.MATERIAL TO qualis;
GRANT SELECT ON DBAMV.ITCULTURA TO qualis;
GRANT SELECT ON DBAMV.GERMES_CULTURA TO qualis;
GRANT SELECT ON DBAMV.LEITO TO qualis;
GRANT SELECT ON DBAMV.CULTURA TO qualis;
GRANT SELECT ON DBAMV.ANTIMICROB TO qualis;
GRANT SELECT ON DBAMV.PW_REGISTRO_ALTA TO qualis;
GRANT SELECT ON DBAMV.MOT_ALT TO qualis;