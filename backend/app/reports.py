import calendar
from io import BytesIO
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
import reportlab

FONT_ROOT=Path(reportlab.__file__).parent/'fonts'
pdfmetrics.registerFont(TTFont('OfficeSans',str(FONT_ROOT/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('OfficeSans-Bold',str(FONT_ROOT/'VeraBd.ttf')))

MANILA = ZoneInfo('Asia/Manila')


def local(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(MANILA)


def fit(c, text, x, y, width, size=10, center=False):
    font = 'OfficeSans'
    while c.stringWidth(text, font, size) > width and size > 6:
        size -= .5
    c.setFont(font, size)
    if center:
        c.drawCentredString(x + width / 2, y, text)
    else:
        c.drawString(x, y, text)


def form48(employee, year, month, records, duties, office):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    c.setTitle(f'Form 48 - {employee.name} - {year}-{month:02d}')
    x, w = 25 * mm, 160 * mm
    c.setFont('OfficeSans', 8)
    c.drawString(x, 280 * mm, 'Civil Service Form No. 48')
    c.setFont('OfficeSans-Bold', 15)
    c.drawCentredString(A4[0]/2, 270 * mm, 'DAILY TIME RECORD')
    fit(c, employee.name, x, 257 * mm, w, 12, True)
    c.line(x + 15*mm, 255*mm, x+w-15*mm, 255*mm)
    c.setFont('OfficeSans', 8)
    c.drawCentredString(A4[0]/2, 251*mm, '(Name)')
    c.setFont('OfficeSans', 10)
    c.drawString(x, 243*mm, f'For the month of {calendar.month_name[month]} {year}')
    c.setFont('OfficeSans', 8)
    c.drawString(x, 237*mm, 'Official hours for arrival and departure:')
    c.drawString(x, 232*mm, f'Regular days: {office.am_in} - {office.am_out}; {office.pm_in} - {office.pm_out}')
    c.drawString(x+110*mm, 232*mm, 'Saturdays: __________')
    top, row_h = 227*mm, 4.5*mm
    widths = [12, 29, 29, 29, 29, 16, 16]
    edges = [x]
    for width in widths:
        edges.append(edges[-1] + width*mm)
    bottom = top - 2*row_h - 31*row_h
    c.setLineWidth(.5)
    c.rect(x, bottom, w, top-bottom)
    for edge in edges[1:-1]:
        c.line(edge, top-row_h if edge in (edges[2], edges[4], edges[6]) else top, edge, bottom)
    c.line(edges[1], top-row_h, edges[-1], top-row_h)
    for n in range(32):
        y = top-(2+n)*row_h
        c.line(x, y, x+w, y)
    c.setFont('OfficeSans', 8)
    c.drawCentredString((edges[0]+edges[1])/2, top-1.4*row_h, 'Day')
    for start, end, label in [(1,3,'A.M.'),(3,5,'P.M.'),(5,7,'Undertime')]:
        c.drawCentredString((edges[start]+edges[end])/2, top-.75*row_h, label)
    for index, label in enumerate(['Arrival','Departure','Arrival','Departure','Hours','Minutes'],1):
        c.drawCentredString((edges[index]+edges[index+1])/2, top-1.8*row_h, label)
    slots = {(r.work_date.day, r.action): r for r in records}
    for day in range(1,32):
        y = top-(2+day)*row_h+1.4*mm
        c.drawCentredString((edges[0]+edges[1])/2, y, str(day))
        if day <= calendar.monthrange(year, month)[1]:
            for index, action in enumerate(['am_in','am_out','pm_in','pm_out'],1):
                record = slots.get((day, action))
                if record:
                    c.drawCentredString((edges[index]+edges[index+1])/2, y, local(record.recorded_at).strftime('%I:%M').lstrip('0'))
    c.setFont('OfficeSans', 9)
    c.drawString(x+3*mm, bottom-5*mm, 'TOTAL')
    c.line(x, bottom-7*mm, x+w, bottom-7*mm)
    y = bottom-14*mm
    for line in ['I certify on my honor that the above is a true and correct report of the',
                 'hours of work performed, record of which was made daily at the time',
                 'of arrival at and departure from office.']:
        c.drawString(x+4*mm, y, line)
        y -= 4*mm
    c.line(x+35*mm, y-10*mm, x+w-35*mm, y-10*mm)
    c.drawCentredString(A4[0]/2, y-14*mm, 'Employee signature')
    c.drawString(x+4*mm, y-23*mm, 'Verified as to the prescribed office hours:')
    fit(c, office.signatory or '____________________________', x+25*mm, y-34*mm, w-50*mm, 10, True)
    fit(c, office.signatory_title, x+25*mm, y-39*mm, w-50*mm, 9, True)
    if duties:
        c.showPage()
        c.setFont('OfficeSans-Bold', 14)
        c.drawString(x, 277*mm, 'Field-duty summary')
        fit(c, f'{employee.name} | {calendar.month_name[month]} {year}', x, 268*mm, w, 11)
        c.setFont('OfficeSans', 9)
        c.drawString(x, 260*mm, 'Supplementary record; approvals do not create arrival/departure times.')
        y = 248*mm
        import textwrap
        for duty in sorted(duties, key=lambda d:d.work_date):
            lines = [f'{duty.work_date:%d %b} - {duty.period.replace("_", " ").title()}']
            lines += textwrap.wrap('Location: '+duty.location, 85)
            lines += textwrap.wrap('Purpose: '+duty.purpose, 85)
            if y-len(lines)*5*mm < 20*mm:
                c.showPage()
                y=275*mm
            c.setFont('OfficeSans', 9)
            for line in lines:
                c.drawString(x, y, line)
                y-=5*mm
            y-=4*mm
    c.save()
    return output.getvalue()
