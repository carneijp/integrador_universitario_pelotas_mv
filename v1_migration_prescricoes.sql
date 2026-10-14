CREATE TABLE DBAMV.prescription_qualis (
    "PRESCR_ID" VARCHAR2(20), 
    "CD_MEDICO" VARCHAR2(10), 
    "DT_LIBERACAO" DATE, 
    "DT_SUSPENSAO" DATE, 
    "NR_ATENDIMENTO" VARCHAR2(16), 
    "PRESCR_ID_ON_QUALIS" VARCHAR2(32), 
    "PRESCR_STATUS" VARCHAR2(2), 
    "PRESCR_SENDED_STATUS" VARCHAR2(2), 
    "PRESCR_SENDED_MESSAGE" VARCHAR2(4000), 
    "HOSPITAL_UNITY_ID" VARCHAR2(11), 
    "ADMISSION_DATE" DATE, 
    "INFECTION_DATE" DATE, 
    "CLINICAL_HISTORY" VARCHAR2(2000), 
    "DS_OBS_ENFERMAGEM" VARCHAR2(2000), 
    "DS_JUSTIFICATIVA" VARCHAR2(2000), 
    "PATIENT_HOSPITAL_ID" VARCHAR2(10), 
    "PATIENT_HEIGHT" VARCHAR2(10), 
    "PATIENT_WEIGHT" VARCHAR2(11), 
    "ID_INFECTION" VARCHAR2(20), 
    "INFECTION_NAME" VARCHAR2(256), 
    "BODY_SENDED" LONG,
    "DT_ENVIO" DATE,
    "DT_RETORNO" DATE,
    PRIMARY KEY ("PRESCR_ID")
);

CREATE INDEX prescription_qualis_idx ON prescription_qualis(prescr_id, prescr_sended_status, prescr_status, dt_liberacao, dt_suspensao);

CREATE TABLE qualis_trigger_execution (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome_trigger VARCHAR2(100),
    inicio TIMESTAMP,
    fim TIMESTAMP,
    duracao_ms NUMBER,
    execution_status VARCHAR2(4000)
);

CREATE OR REPLACE PROCEDURE dbamv.log_qualis_trigger_execution (
    p_nome_trigger     IN VARCHAR2,
    p_inicio           IN TIMESTAMP,
    p_execution_status IN VARCHAR2
) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_fim TIMESTAMP := SYSTIMESTAMP;
BEGIN
    INSERT INTO DBAMV.qualis_trigger_execution (
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
        SUBSTRB(p_execution_status, 1, 4000)
    );
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END log_qualis_trigger_execution;
/

CREATE OR REPLACE TRIGGER DBAMV.copy_prescr_medica_qualis
AFTER INSERT ON DBAMV.PRE_MED
REFERENCING NEW AS nova
FOR EACH ROW
DECLARE
  v_inicio TIMESTAMP := SYSTIMESTAMP;
  v_status VARCHAR2(32767) := 'SUCCESS';
BEGIN
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
        WHERE A.cd_atendimento = :nova.cd_atendimento;
    EXCEPTION
        WHEN OTHERS THEN
            v_status := 'ERROR: ' || DBMS_UTILITY.FORMAT_ERROR_STACK;
    END;

    -- nenhum erro da integração (nem do log) pode impedir o MV de gravar a prescrição
    BEGIN
        dbamv.log_qualis_trigger_execution('copy_prescr_medica_qualis', v_inicio, v_status);
    EXCEPTION
        WHEN OTHERS THEN
            NULL;
    END;
END;
/

CREATE OR REPLACE TRIGGER dbamv.update_presc_qualis
AFTER UPDATE OF dh_impressao ON dbamv.PRE_MED
REFERENCING NEW AS nova OLD AS velha
FOR EACH ROW
DECLARE
  v_inicio TIMESTAMP := SYSTIMESTAMP;
  v_status VARCHAR2(32767) := 'SUCCESS';
BEGIN
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
            AND EXISTS (SELECT 1 FROM DBAMV.ATENDIME A WHERE A.cd_atendimento = :nova.cd_atendimento);
    EXCEPTION
        WHEN OTHERS THEN
            v_status := 'ERROR: ' || DBMS_UTILITY.FORMAT_ERROR_STACK;
    END;

    -- nenhum erro da integração (nem do log) pode impedir o MV de gravar a prescrição
    BEGIN
        dbamv.log_qualis_trigger_execution('update_presc_qualis', v_inicio, v_status);
    EXCEPTION
        WHEN OTHERS THEN
            NULL;
    END;
END;
/