CREATE OR REPLACE PROCEDURE dbamv.log_qualis_trigger_execution (
    p_nome_trigger     IN VARCHAR2,
    p_inicio           IN TIMESTAMP,
    p_execution_status IN VARCHAR2
) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_fim TIMESTAMP := SYSTIMESTAMP;
BEGIN
    INSERT INTO qualis_trigger_execution (
        nome_trigger,
        inicio,
        fim,
        duracao_ms,
        execution_status
    )
    VALUES (
        p_nome_trigger,
        p_inicio,
        v_fim,
        EXTRACT(SECOND FROM (v_fim - p_inicio)) * 1000,
        p_execution_status
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        -- log nunca pode derrubar a transação de quem chamou
        ROLLBACK;
END log_qualis_trigger_execution;

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
    
    dbamv.log_qualis_trigger_execution('CAPTURE_CULTURA_TO_QUALIS', v_inicio, 'SUCCESS');
EXCEPTION
      WHEN OTHERS THEN
      dbamv.log_qualis_trigger_execution('CAPTURE_CULTURA_TO_QUALIS', v_inicio, 'ERROR');
END;

CREATE OR REPLACE TRIGGER DBAMV.UPDATE_CULTURA_TO_QUALIS
FOR INSERT OR UPDATE ON DBAMV.ITCULTURA
COMPOUND TRIGGER
    v_inicio TIMESTAMP;
    v_tab DBAMV.TYPE_QUALIS_BACT_KEY_TABLE := DBAMV.TYPE_QUALIS_BACT_KEY_TABLE();
 
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
 
    dbamv.log_qualis_trigger_execution('update_cultura_to_qualis', v_inicio, 'SUCCESS');
EXCEPTION
    WHEN OTHERS THEN
        dbamv.log_qualis_trigger_execution('update_cultura_to_qualis', v_inicio, 'ERROR');
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
    
    dbamv.log_qualis_trigger_execution('copy_prescr_medica_qualis', v_inicio, 'SUCCESS');
EXCEPTION
    WHEN OTHERS THEN
        dbamv.log_qualis_trigger_execution('copy_prescr_medica_qualis', v_inicio, 'ERROR');
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
    
    dbamv.log_qualis_trigger_execution('update_presc_qualis', v_inicio, 'SUCCESS');
EXCEPTION
    WHEN OTHERS THEN
        dbamv.log_qualis_trigger_execution('update_presc_qualis', v_inicio, 'ERROR');
END;

----- Queries de teste

SELECT 
  nome_trigger,
  Min(duracao_ms) AS minimo,
  Max(duracao_ms) AS maximo,
  Avg(duracao_ms) AS media, 
  Count(*) AS vezes
FROM dbamv.qualis_trigger_execution
GROUP BY nome_trigger;

SELECT * FROM dbamv.bacteriology_qualis;
SELECT * FROM dbamv.prescription_qualis;

INSERT INTO dbamv.bacteriology_qualis( cd_ped_lab, cd_exa_lab, cd_itped_lab, bacteriology_sended_status)
SELECT 
  cd_ped_lab, cd_exa_lab, cd_itped_lab, '0' 
FROM dbamv.cultura c
  WHERE cd_ped_lab|| '_' || cd_exa_lab|| '_' || cd_itped_lab NOT IN (SELECT cd_ped_lab|| '_' || cd_exa_lab|| '_' || cd_itped_lab FROM dbamv.bacteriology_qualis)
    AND c.tp_resultado = 'P';