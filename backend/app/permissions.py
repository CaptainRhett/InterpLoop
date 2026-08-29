from flask import abort
from sqlalchemy import and_, false, or_

from .models import (
    CourseEnrollment,
    FeedbackContext,
    FeedbackLog,
    PracticeContext,
    PracticeSession,
    TeachingAssignment,
    User,
    db,
)


def is_admin(user):
    return bool(user and user.role == "admin")


def is_teacher(user):
    return bool(user and user.role == "teacher")


def _teacher_student_ids(user):
    return (
        db.session.query(CourseEnrollment.student_id)
        .join(
            TeachingAssignment,
            and_(
                TeachingAssignment.class_id == CourseEnrollment.class_id,
                TeachingAssignment.course_id == CourseEnrollment.course_id,
                TeachingAssignment.is_active.is_(True),
            ),
        )
        .filter(
            TeachingAssignment.teacher_id == user.id,
            CourseEnrollment.is_active.is_(True),
        )
    )


def scope_user_query(query, actor):
    if is_admin(actor):
        return query
    if is_teacher(actor):
        return query.filter(User.id.in_(_teacher_student_ids(actor)))
    return query.filter(User.id == actor.id)


def scope_practice_query(query, actor):
    if is_admin(actor):
        return query
    if actor.role == "student":
        return query.filter(PracticeSession.user_id == actor.id)
    if not is_teacher(actor):
        return query.filter(false())

    assigned_context = (
        db.session.query(TeachingAssignment.id)
        .filter(
            TeachingAssignment.teacher_id == actor.id,
            TeachingAssignment.class_id == PracticeContext.class_id,
            TeachingAssignment.course_id == PracticeContext.course_id,
            TeachingAssignment.is_active.is_(True),
        )
        .exists()
    )
    return query.outerjoin(
        PracticeContext, PracticeContext.session_id == PracticeSession.id
    ).filter(
        or_(
            and_(PracticeContext.id.isnot(None), assigned_context),
            and_(
                PracticeContext.id.is_(None),
                PracticeSession.user_id.in_(_teacher_student_ids(actor)),
            ),
        )
    )


def scope_feedback_query(query, actor):
    if is_admin(actor):
        return query
    if actor.role == "student":
        return query.filter(FeedbackLog.user_id == actor.id)
    if not is_teacher(actor):
        return query.filter(false())

    assigned_context = (
        db.session.query(TeachingAssignment.id)
        .filter(
            TeachingAssignment.teacher_id == actor.id,
            TeachingAssignment.class_id == FeedbackContext.class_id,
            TeachingAssignment.course_id == FeedbackContext.course_id,
            TeachingAssignment.is_active.is_(True),
        )
        .exists()
    )
    return query.outerjoin(
        FeedbackContext, FeedbackContext.feedback_log_id == FeedbackLog.id
    ).filter(
        or_(
            and_(FeedbackContext.id.isnot(None), assigned_context),
            and_(
                FeedbackContext.id.is_(None),
                FeedbackLog.user_id.in_(_teacher_student_ids(actor)),
            ),
        )
    )


def practice_for_user(session_id, actor):
    item = scope_practice_query(PracticeSession.query, actor).filter(
        PracticeSession.id == session_id
    ).first()
    if not item:
        existing = db.session.get(PracticeSession, session_id)
        if existing:
            abort(403, "无权访问该练习记录")
        abort(404, "练习记录不存在")
    return item


def user_learning_contexts(user):
    if user.role == "student":
        rows = CourseEnrollment.query.filter_by(student_id=user.id, is_active=True).all()
        rows = [
            row
            for row in rows
            if row.class_group.is_active and row.course.is_active and row.course.term.is_active
        ]
        return [
            {
                "enrollment_id": row.id,
                "term": row.course.term.to_dict(),
                "class_group": row.class_group.to_dict(),
                "course": row.course.to_dict(),
            }
            for row in rows
        ]
    if user.role == "teacher":
        rows = TeachingAssignment.query.filter_by(teacher_id=user.id, is_active=True).all()
        rows = [
            row
            for row in rows
            if row.class_group.is_active and row.course.is_active and row.course.term.is_active
        ]
        return [
            {
                "assignment_id": row.id,
                "term": row.course.term.to_dict(),
                "class_group": row.class_group.to_dict(),
                "course": row.course.to_dict(),
            }
            for row in rows
        ]
    return []


def managed_student_contexts(actor):
    query = CourseEnrollment.query.filter_by(is_active=True)
    if is_teacher(actor):
        query = query.join(
            TeachingAssignment,
            and_(
                TeachingAssignment.class_id == CourseEnrollment.class_id,
                TeachingAssignment.course_id == CourseEnrollment.course_id,
            ),
        ).filter(
            TeachingAssignment.teacher_id == actor.id,
            TeachingAssignment.is_active.is_(True),
        )
    elif not is_admin(actor):
        query = query.filter(CourseEnrollment.student_id == actor.id)
    rows = [
        row
        for row in query.order_by(CourseEnrollment.id.desc()).all()
        if row.class_group.is_active and row.course.is_active and row.course.term.is_active
    ]
    return [
        {
            "enrollment_id": row.id,
            "student": row.student.to_dict(),
            "term": row.course.term.to_dict(),
            "class_group": row.class_group.to_dict(),
            "course": row.course.to_dict(),
        }
        for row in rows
    ]


def resolve_student_enrollment(user, class_id=None, course_id=None):
    query = CourseEnrollment.query.filter_by(student_id=user.id, is_active=True)
    if class_id is not None:
        query = query.filter(CourseEnrollment.class_id == class_id)
    if course_id is not None:
        query = query.filter(CourseEnrollment.course_id == course_id)
    rows = query.all()
    if not rows:
        abort(403, "账号未分配到该班级和课程")
    if class_id is None or course_id is None:
        if len(rows) != 1:
            abort(400, "请选择本次练习所属的班级和课程")
    enrollment = rows[0]
    if enrollment.class_group.term_id != enrollment.course.term_id:
        abort(400, "班级和课程不属于同一学期")
    if (
        not enrollment.class_group.is_active
        or not enrollment.course.is_active
        or not enrollment.course.term.is_active
    ):
        abort(403, "该学期、班级或课程已停用")
    return enrollment
