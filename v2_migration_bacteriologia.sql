CREATE TABLE DBAMV.BACTERIOLOGY_QUALIS(	
    CD_PED_LAB NUMBER(10,0), 
    CD_EXA_LAB NUMBER(4,0) NOT NULL, 
    CD_ITPED_LAB NUMBER(8, 0) NOT NULL,
    ID_BACTERIOLOGY_QUALIS VARCHAR2(255), 
    BODY_SENDED VARCHAR2(4000), 
    RESPONSE_RECIEVED VARCHAR2(4000),
    BACTERIOLOGY_SENDED_STATUS VARCHAR2(2)
);
ALTER TABLE DBAMV.BACTERIOLOGY_QUALIS ADD CONSTRAINT PK_BACTERIOLOGY_QUALIS PRIMARY KEY (CD_PED_LAB, CD_EXA_LAB, CD_ITPED_LAB);

CREATE TYPE DBAMV.TYPE_QUALIS_BACT_KEY AS OBJECT (
    CD_PED_LAB NUMBER,
    CD_EXA_LAB NUMBER,
    CD_ITPED_LAB NUMBER
);
CREATE TYPE DBAMV.TYPE_QUALIS_BACT_KEY_TABLE AS TABLE OF DBAMV.TYPE_QUALIS_BACT_KEY;

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