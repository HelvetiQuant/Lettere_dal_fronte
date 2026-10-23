-- Helper function for executing arbitrary SQL via PostgREST RPC
CREATE OR REPLACE FUNCTION exec_sql(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    result json;
BEGIN
    EXECUTE query;
    RETURN json_build_object('ok', true);
EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object('ok', false, 'error', SQLERRM, 'detail', SQLSTATE);
END;
$$;
