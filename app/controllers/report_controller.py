from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import TestSession, Report
from app.services.report_service import ReportService

report_bp = Blueprint('report', __name__)

@report_bp.route('/result/<int:session_id>')
@login_required
def show_result(session_id):
    session = TestSession.query.get_or_404(session_id)
    
    # Kullanıcı sadece kendi raporunu görebilir
    if session.user_id != current_user.id:
        return "Yetkisiz Erişim", 403

    # Rapor daha önce oluşturulmuş mu?
    report = Report.query.filter_by(session_id=session.id).first()
    
    # Oluşturulmamışsa şimdi oluştur (AI devreye girer)
    if not report:
        report = ReportService.generate_report(session)
    
    return render_template('result.html', report=report, session=session)