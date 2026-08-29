from flask import has_request_context, request

from .models import AuditLog, db


def add_audit(actor, action, target_type=None, target_id=None, details=None):
    item = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
        ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(item)
    return item
