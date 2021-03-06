from flask import render_template, jsonify, Response, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from . import registration_blueprint
from .models import Registration, Uni
from app.user import groups_sufficient
from app.db import db
import io
import csv

EXKURSIONEN_TYPES = {
  'egal': ('ist mir egal', -1, 'Egal'),
  'keine': ('keine exkursion', -1, 'Keine'),
  'mpi': ('Max-Planck-Institut für Kolloid- und Grenzflächenforschung', 15, 'MPI Kollid-/Grenzflächenf.'),
  'awi': ('Alfred-Wegner-Institut', 15, 'AWI'),
  'spectrum': ('Technikmuseum und Science Center Spectrum', 50, 'Technikmuseum'),
  'naturkunde': ('Naturkundemuseum', 30, 'Naturkundemuseum'),
  'bessy': ('Helmholtz-Zentrum Berlin mit BESSY II', 20, 'BESSY'),
  'fub': ('Uni-Tour: Freie Universität Berlin', 0, 'FUB'),
  'tub': ('Uni-Tour: Technische Universität Berlin', 0, 'TUB'),
  'golm': ('Uni-Tour: Uni Potsdam in Golm (+ neues Palais)', 0, 'UP'),
  'adlershof': ('Wissenschaftscampus Adlershof', 0, 'Adlershof'),
  'stad': ('Klassische Stadtführung mit Reichstagsbesichtigung', 25, 'Klass. Stadtf.'),
  'hipster': ('Alternative Stadtführung', 20, 'Altern. Stadtf.'),
  'unterwelten': ('Berliner Unterwelten', 20, 'Unterwelten'),
  'potsdam': ('Schlösser und Gärten Tour Potsdam', 25, 'Schlösser Potsdam'),
  'workshop': ('Workshop "Aufstehen gegen Rassismus"', 25, 'Workshop Rassismus'),
  'nospace': ('Konnte keiner Exkursion zugeordnet werden', -1, 'Noch offen'),
}

EXKURSIONEN_FIELD_NAMES = ['exkursion1', 'exkursion2', 'exkursion3', 'exkursion4']

EXKURSIONEN_TYPES_BIRTHDAY = ['stad', 'bessy']

EXKURSIONEN_TYPES_FORM = [('nooverwrite', '')] + [(name, data[0]) for name, data in EXKURSIONEN_TYPES.items()]

TSHIRTS_TYPES = {
  'keins': 'Nein, ich möchte keins',
  'fitted_5xl': 'fitted 5XL',
  'fitted_4xl': 'fitted 4XL',
  'fitted_3xl': 'fitted 3XL',
  'fitted_xxl': 'fitted XXL',
  'fitted_xl': 'fitted XL',
  'fitted_l': 'fitted L',
  'fitted_m': 'fitted M',
  'fitted_s': 'fitted S',
  'fitted_xs': 'fitted XS',
  '5xl': '5XL',
  '4xl': '4XL',
  '3xl': '3XL',
  'xxl': 'XXL',
  'xl': 'XL',
  'l': 'L',
  'm': 'M',
  's': 'S',
  'xs': 'XS'
}

ESSEN_TYPES = {
  'vegetarisch': 'Vegetarisch',
  'vegan': 'Vegan',
  'omnivor': 'Omnivor'
}

ZELTEN_TYPES = {
  'nein': 'nein',
  'ja_eigenes_zelt': 'ja, bringe mein eigenes Zelt mit',
  'ja_kein_zelt': 'ja, habe aber kein eigenes Zelt.'
}

HEISSE_GETRAENKE_TYPES = {
  'egal': 'Egal',
  'kaffee': 'Kaffee',
  'tee': 'Tee'
}

class Sommer17ExkursionenOverwriteForm(FlaskForm):
    spitzname = StringField('Spitzname')
    exkursion_overwrite = SelectField('Exkursionen Festlegung', choices=EXKURSIONEN_TYPES_FORM)
    submit = SubmitField()

def sose17_calculate_exkursionen(registrations):
    def get_sort_key(reg):
        return reg.id
    result = {}
    regs_later = []
    regs_overwritten = [reg for reg in registrations
                            if 'exkursion_overwrite' in reg.data and reg.data['exkursion_overwrite'] != 'nooverwrite']
    regs_normal = sorted(
                    [reg for reg in registrations
                         if not ('exkursion_overwrite' in reg.data) or reg.data['exkursion_overwrite'] == 'nooverwrite'],
                    key = get_sort_key
                  )
    for type_name, type_data in EXKURSIONEN_TYPES.items():
        result[type_name] = {'space': type_data[1], 'free': type_data[1], 'registrations': []}
    for reg in regs_overwritten:
        exkursion_selected = reg.data['exkursion_overwrite']
        if not result[exkursion_selected]:
            return None
        result[exkursion_selected]['registrations'].append((reg, -1))
        result[exkursion_selected]['free'] -= 1
    for reg in regs_normal:
        if reg.uni.name == 'Alumni':
            regs_later.append(reg)
            continue;
        got_slot = False
        for field_index, field in enumerate(EXKURSIONEN_FIELD_NAMES):
            exkursion_selected = reg.data[field]
            if not result[exkursion_selected]:
                return None
            if result[exkursion_selected]['space'] == -1 or result[exkursion_selected]['free'] > 0:
                result[exkursion_selected]['registrations'].append((reg, field_index))
                result[exkursion_selected]['free'] -= 1
                got_slot = True
                break;
        if not got_slot:
            result['nospace']['registrations'].append((reg, len(EXKURSIONEN_FIELD_NAMES) + 1))
    for reg in regs_later:
        for field_index, field in enumerate(EXKURSIONEN_FIELD_NAMES):
            exkursion_selected = reg.data[field]
            if not result[exkursion_selected]:
                return None
            if result[exkursion_selected]['space'] == -1 or result[exkursion_selected]['free'] > 0:
                result[exkursion_selected]['registrations'].append((reg, field_index))
                result[exkursion_selected]['free'] -= 1
                break;
    return result

@registration_blueprint.route('/admin/registration/report/sose17')
@groups_sufficient('admin', 'orga')
def registration_sose17_reports():
    return render_template('admin/sose17/reports.html')

@registration_blueprint.route('/admin/registration/report/sose17/exkursionen')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_exkursionen():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    result = sose17_calculate_exkursionen(registrations)
    return render_template('admin/sose17/exkursionen.html',
        result = result,
        exkursionen_types = EXKURSIONEN_TYPES,
        exkursionen_types_birthday = EXKURSIONEN_TYPES_BIRTHDAY
    )

@registration_blueprint.route('/admin/registration/report/sose17/t-shirts')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_tshirts():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    unis = Uni.query.order_by(Uni.id)
    result = {}
    result_unis = {}
    for uni in unis:
        result_unis[uni.id] = {
            'name': uni.name,
            'registrations': [],
            'types': {name: 0 for name, label in TSHIRTS_TYPES.items()}
        }
    for name, label in TSHIRTS_TYPES.items():
        result[name] = {'label': label, 'registrations': []}
    for reg in registrations:
        tshirt_size = reg.data['tshirt']
        if not result[tshirt_size]:
            return None
        result[tshirt_size]['registrations'].append(reg)
        result_unis[reg.uni.id]['registrations'].append(reg)
        result_unis[reg.uni.id]['types'][tshirt_size] += 1
    return render_template('admin/sose17/t-shirts.html',
        result = result,
        result_unis = result_unis,
        TSHIRTS_TYPES = TSHIRTS_TYPES
    )

@registration_blueprint.route('/admin/registration/report/sose17/essen')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_essen():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    result_essen = {}
    result_heisse_getraenke = {}
    result_getraenkewunsch = []
    result_allergien = []
    for name, label in ESSEN_TYPES.items():
        result_essen[name] = {'label': label, 'registrations': []}
    for name, label in HEISSE_GETRAENKE_TYPES.items():
        result_heisse_getraenke[name] = {'label': label, 'registrations': []}
    for reg in registrations:
        essen_type = reg.data['essen']
        heisse_getraenke = reg.data['heissgetraenk']
        getraenkewunsch = reg.data['getraenk']
        allergien = reg.data['allergien']
        if not result_essen[essen_type] or not result_heisse_getraenke[heisse_getraenke]:
            return None
        result_essen[essen_type]['registrations'].append(reg)
        result_heisse_getraenke[heisse_getraenke]['registrations'].append(reg)
        if getraenkewunsch:
            result_getraenkewunsch.append(reg)
        if allergien:
            result_allergien.append(reg)
    return render_template('admin/sose17/essen.html',
        result_essen = result_essen,
        result_heisse_getraenke = result_heisse_getraenke,
        result_getraenkewunsch = result_getraenkewunsch,
        result_allergien = result_allergien
    )

@registration_blueprint.route('/admin/registration/report/sose17/rahmenprogramm')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_rahmenprogramm():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    result_alkoholfrei = []
    result_musikwunsch = []
    for reg in registrations:
        alkoholfrei = reg.data['alkoholfrei']
        musikwunsch = reg.data['musikwunsch']
        if alkoholfrei:
            result_alkoholfrei.append(reg)
        if musikwunsch:
            result_musikwunsch.append(reg)
    return render_template('admin/sose17/rahmenprogramm.html',
        result_alkoholfrei = result_alkoholfrei,
        result_musikwunsch = result_musikwunsch
    )

@registration_blueprint.route('/admin/registration/report/sose17/spitznamen')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_spitznamen():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    result = {'with': [], 'without': []}
    for reg in registrations:
        spitzname = reg.data['spitzname']
        if spitzname and spitzname != "-":
            result['with'].append(reg)
        else:
            result['without'].append(reg)
    return render_template('admin/sose17/spitznamen.html',
        result = result
    )

@registration_blueprint.route('/admin/registration/report/sose17/orgaprobleme')
@groups_sufficient('admin', 'orga')
def registration_sose17_report_orgaprobleme():
    registrations = [reg for reg in Registration.query.order_by(Registration.id) if reg.is_zapf_attendee]
    result = []
    for reg in registrations:
        if reg.data['orgaprobleme']:
            result.append(reg)
    return render_template('admin/sose17/orgaprobleme.html',
        result = result
    )

@registration_blueprint.route('/admin/registration/<int:reg_id>/details_sose17', methods=['GET', 'POST'])
@groups_sufficient('admin', 'orga')
def registration_sose17_details_registration(reg_id):
    reg = Registration.query.filter_by(id=reg_id).first()
    form = Sommer17ExkursionenOverwriteForm()
    if form.validate_on_submit():
        data = reg.data
        old_spitzname = data['spitzname']
        if 'exkursion_overwrite' in reg.data:
            old_overwrite = data['exkursion_overwrite']
        data['spitzname'] = form.spitzname.data
        data['exkursion_overwrite'] = form.exkursion_overwrite.data
        reg.data = data
        db.session.add(reg)
        db.session.commit()
        if old_spitzname != form.spitzname.data:
            return redirect(url_for('registration.registration_sose17_report_spitznamen'))
        elif old_overwrite and old_overwrite != form.exkursion_overwrite.data:
            return redirect(url_for('registration.registration_sose17_report_exkursionen'))
        else:
            return redirect(url_for('registration.registration_sose17_details_registration', reg_id = reg_id))
    if 'exkursion_overwrite' in reg.data:
        form.exkursion_overwrite.data = reg.data['exkursion_overwrite']
    form.spitzname.data = reg.data['spitzname']
    return render_template('admin/sose17/details.html',
        reg = reg,
        form = form,
        EXKURSIONEN_TYPES = EXKURSIONEN_TYPES,
        ESSEN_TYPES = ESSEN_TYPES,
        TSHIRTS_TYPES = TSHIRTS_TYPES,
        ZELTEN_TYPES = ZELTEN_TYPES,
        HEISSE_GETRAENKE_TYPES = HEISSE_GETRAENKE_TYPES
    )

@registration_blueprint.route('/admin/registration/report/sose17/stimmkarten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_stimmkarten_latex():
    unis = Uni.query.all()
    result = []
    for uni in unis:
        uni_regs = [reg for reg in Registration.query.filter_by(uni_id = uni.id) if reg.is_zapf_attendee]
        if len(uni_regs) > 0:
            result.append("\\stimmkarte{{{0}}}".format(uni.name))
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/idkarten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_idkarten_latex():
    result = ["\\idcard{{{}}}{{{}}}{{{}}}".format(reg.id, reg.user.full_name, reg.uni.name)
                for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/tagungsausweise/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_tagungsausweise_latex():
    def get_sort_key(entry):
        return entry[0]
    registrations = [reg for reg in Registration.query.all() if reg.is_zapf_attendee]
    result_exkursionen = sose17_calculate_exkursionen(registrations)
    result = []
    result_alumni = []
    for name, data in result_exkursionen.items():
        for reg in data['registrations']:
            if reg[0].uni.name == "Alumni":
                ausweis_type = "\\ausweisalumni"
            else:
                ausweis_type = "\\ausweis"
            result.append((reg[0].uni_id, "{type}{{{spitzname}}}{{{name}}}{{{uni}}}{{{id}}}{{{exkursion}}}".format(
              type = ausweis_type,
              spitzname = reg[0].data['spitzname'] or reg[0].user.firstName,
              name = reg[0].user.full_name,
              uni = reg[0].uni.name,
              id = reg[0].id,
              exkursion = EXKURSIONEN_TYPES[name][2]
            )))
    result = sorted(result, key = get_sort_key)
    result = [data[1] for data in result]
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/strichlisten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_strichlisten_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    i = 0
    result = []
    for reg in registrations:
        if i == 0:
            result.append("\\strichliste{")
        result.append("{} & {} & \\\\[0.25cm] \\hline".format(reg.user.full_name, reg.uni.name))
        i += 1
        if i == 34:
            result.append("}")
            i = 0
    result.append("}")
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/bmbflisten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_bmbflisten_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    i = 0
    lfd_nr = 1
    result = []
    for reg in registrations:
        if reg.uni.name == "Alumni":
            continue;
        if i == 0:
            result.append("\\bmbfpage{")
        result.append("{} & {} & {} &&& \\\\[0.255cm] \\hline".format(lfd_nr, reg.user.full_name, reg.uni.name))
        i += 1
        lfd_nr += 1
        if i == 20:
            result.append("}")
            i = 0
    result.append("}")
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/taschentassenlisten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_taschentassenlisten_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    i = 0
    result = []
    for reg in registrations:
        if i == 0:
            result.append("\\tassentaschen{")
        result.append("{} & {} && \\\\[0.25cm] \\hline".format(reg.user.full_name, reg.uni.name))
        i += 1
        if i == 34:
            result.append("}")
            i = 0
    if i != 0:
        result.append("}")
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/ausweisidbeitraglisten/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_ausweisidbeitraglisten_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    i = 0
    result = []
    for reg in registrations:
        if i == 0:
            result.append("\\ausweisidbeitrag{")
        result.append("{} & {} &&& \\\\[0.25cm] \\hline".format(reg.user.full_name, reg.uni.name))
        i += 1
        if i == 34:
            result.append("}")
            i = 0
    if i != 0:
        result.append("}")
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/t-shirt/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_t_shirt_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    i = 0
    result = []
    for reg in registrations:
        if i == 0:
            result.append("\\tshirt{")
        result.append("{} & {} & {} \\\\[0.25cm] \\hline".format(reg.user.full_name, reg.uni.name, reg.data["tshirt"]))
        i += 1
        if i == 34:
            result.append("}")
            i = 0
    if i != 0:
        result.append("}")
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/wichteln/csv')
@groups_sufficient('admin', 'orga')
def registrations_sose17_export_wichteln_csv():
    registrations = Registration.query.all()
    result = io.StringIO()
    writer = csv.writer(result, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerows([[reg.user.full_name, reg.uni.name, reg.data['spitzname']]
                      for reg in registrations if reg.is_zapf_attendee])
    return Response(result.getvalue(), mimetype='text/csv')

@registration_blueprint.route('/admin/registration/report/sose17/exkursionen/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_exkursionen_latex():
    registrations = [reg for reg in Registration.query.all() if reg.is_zapf_attendee]
    result_exkursionen = sose17_calculate_exkursionen(registrations)
    result = []
    for name, data in result_exkursionen.items():
        buffer = ["\\exkursionspage{{{type}}}{{".format(type=EXKURSIONEN_TYPES[name][2])]
        for reg in data['registrations']:
            buffer.append("{} & {} \\\\ \\hline".format(reg[0].user.full_name, reg[0].uni.name))
        buffer.append("}")
        result.append("\n".join(buffer))
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/unis/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_unis_latex():
    unis = Uni.query.all()
    result = []
    for uni in unis:
        uni_regs = [reg for reg in Registration.query.filter_by(uni_id = uni.id) if reg.is_zapf_attendee]
        if len(uni_regs) > 0:
            result.append("\\item{{{0}}}".format(uni.name))
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/unis-teilnehmer/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_unis_teilnehmer_latex():
    unis = Uni.query.all()
    result = []
    for uni in unis:
        uni_regs = [reg for reg in Registration.query.filter_by(uni_id = uni.id) if reg.is_zapf_attendee]
        if len(uni_regs) > 0:
            result.append("\\item{{{0} - {1}}}".format(uni.name, len(uni_regs)))
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/bestaetigungen/latex')
@groups_sufficient('admin', 'orga')
def registration_sose17_export_bestaetigungen_latex():
    registrations = [reg for reg in Registration.query.order_by(Registration.uni_id) if reg.is_zapf_attendee]
    result = []
    for reg in registrations:
        result.append("\\bestaetigung{{{}}}{{{}}}".format(reg.user.full_name, reg.uni.name))
    return Response("\n".join(result), mimetype="application/x-latex")

@registration_blueprint.route('/admin/registration/report/sose17/id_name/csv')
@groups_sufficient('admin', 'orga')
def registrations_sose17_export_id_name_csv():
    registrations = Registration.query.all()
    result = io.StringIO()
    writer = csv.writer(result, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerows([[reg.id, "{} ({})".format(reg.user.full_name, reg.uni.name)]
                      for reg in registrations if reg.is_zapf_attendee])
    return Response(result.getvalue(), mimetype='text/csv')
