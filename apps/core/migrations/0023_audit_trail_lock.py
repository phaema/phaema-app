# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lock the audit trail in the database itself, so rows cannot be changed or removed even with direct database access
through the application's own connection.

Allowed: clearing the user on an entry when that user account is deleted (the entry stays, with no name). A database
administrator carrying out a lawful retention purge can switch the lock off for one transaction with
``SET LOCAL phaema.audit_purge = 'on';`` before the DELETE. That leaves its own trace in the database logs.
"""
from django.db import migrations

LOCK = """
CREATE OR REPLACE FUNCTION phaema_audit_guard() RETURNS trigger AS $$
BEGIN
    IF current_setting('phaema.audit_purge', true) = 'on' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.user_id IS NULL
       AND (to_jsonb(NEW) - 'user_id') = (to_jsonb(OLD) - 'user_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'The PHAEMA audit trail cannot be changed or deleted (%).', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER phaema_audit_no_change
    BEFORE UPDATE OR DELETE ON core_auditentry
    FOR EACH ROW EXECUTE FUNCTION phaema_audit_guard();

CREATE TRIGGER phaema_audit_no_truncate
    BEFORE TRUNCATE ON core_auditentry
    FOR EACH STATEMENT EXECUTE FUNCTION phaema_audit_guard();
"""

UNLOCK = """
DROP TRIGGER IF EXISTS phaema_audit_no_truncate ON core_auditentry;
DROP TRIGGER IF EXISTS phaema_audit_no_change ON core_auditentry;
DROP FUNCTION IF EXISTS phaema_audit_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0022_shared_cache_table")]

    operations = [migrations.RunSQL(LOCK, UNLOCK)]
