-- increment_api_key_usage RPC
--
-- APIキー認証・月次リセット・レート制限チェック・カウントインクリメントを
-- 1トランザクション内でアトミックに実行する。
-- race condition（複数リクエスト同時到達による上限超過）を防ぐ。
--
-- 戻り値:
--   NULL                   → キーが見つからない（認証失敗）
--   {status: rate_limited} → 月次上限超過（429）
--   {status: ok, ...}      → 成功（APIキーレコードの主要フィールドを含む）

CREATE OR REPLACE FUNCTION public.increment_api_key_usage(p_key_hash TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_record api_keys%ROWTYPE;
    v_new_count INT;
BEGIN
    -- FOR UPDATE: 同一キーへの並列アクセスを直列化してrace conditionを防ぐ
    SELECT * INTO v_record
    FROM api_keys
    WHERE key_hash = p_key_hash
      AND is_active = true
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    -- 月次リセット: 前回リセットが今月より前なら req_count を 0 に戻す
    IF DATE_TRUNC('month', v_record.last_reset_at AT TIME ZONE 'UTC')
         < DATE_TRUNC('month', NOW() AT TIME ZONE 'UTC') THEN
        v_record.req_count := 0;
        v_record.last_reset_at := NOW();
    END IF;

    -- レート制限チェック
    IF v_record.req_count >= v_record.req_limit THEN
        RETURN jsonb_build_object(
            'status',     'rate_limited',
            'req_count',  v_record.req_count,
            'req_limit',  v_record.req_limit,
            'plan',       v_record.plan
        );
    END IF;

    v_new_count := v_record.req_count + 1;

    -- アトミックなインクリメント（月次リセット時は last_reset_at も更新）
    UPDATE api_keys
    SET
        req_count      = v_new_count,
        last_reset_at  = v_record.last_reset_at
    WHERE id = v_record.id;

    RETURN jsonb_build_object(
        'status',         'ok',
        'id',             v_record.id,
        'user_email',     v_record.user_email,
        'plan',           v_record.plan,
        'req_count',      v_new_count,
        'req_limit',      v_record.req_limit,
        'last_reset_at',  v_record.last_reset_at,
        'created_at',     v_record.created_at
    );
END;
$$;
