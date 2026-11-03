# SPDX-License-Identifier: AGPL-3.0-or-later
"""The compliance certificates PHAEMA ships with. Administrators can change them and add their own."""
RRO = "Regulatory Reform (Fire Safety) Order 2005"

# code, name, valid (months), statutory, law or standard, has rating, planned task in the maintenance library
TYPES = [
    ("fra", "Fire risk assessment", 12, True, RRO, False, "fra_review"),
    ("fire_alarm", "Fire alarm inspection and service certificate", 6, True, f"{RRO}; BS 5839-1", False, "fire_alarm"),
    ("emergency_lighting", "Emergency lighting test certificate", 12, True, f"{RRO}; BS 5266-1", False,
     "emergency_lighting"),
    ("extinguishers", "Fire extinguisher service record", 12, True, f"{RRO}; BS 5306-3", False, "extinguishers"),
    ("gas", "Gas safety record", 12, True, "Gas Safety (Installation and Use) Regulations 1998", False, "gas_safety"),
    ("eicr", "Electrical installation condition report (EICR)", 60, True,
     "Electricity at Work Regulations 1989; BS 7671", False, "eicr"),
    ("legionella", "Legionella risk assessment", 24, True, "HSE ACoP L8", False, "legionella_ra"),
    ("asbestos", "Asbestos register and management plan review", 12, True,
     "Control of Asbestos Regulations 2012, regulation 4", False, "asbestos"),
    ("lift", "Lift thorough examination report", 6, True, "Lifting Operations and Lifting Equipment Regulations 1998",
     False, "lift_exam"),
    ("pressure", "Pressure system examination report", 12, True, "Pressure Systems Safety Regulations 2000", False,
     "pressure"),
    ("tm44", "Air conditioning inspection report", 60, True,
     "Energy Performance of Buildings (England and Wales) Regulations 2012", False, "aircon_tm44"),
    ("epc", "Energy Performance Certificate (EPC)", 120, True,
     "Energy Performance of Buildings (England and Wales) Regulations 2012", True, ""),
    ("dec", "Display Energy Certificate (DEC)", 12, True,
     "Energy Performance of Buildings (England and Wales) Regulations 2012", True, ""),
]


def ensure_types():
    from .models import ComplianceType

    for i, (code, name, months, statutory, regulation, rating, task) in enumerate(TYPES):
        ComplianceType.objects.get_or_create(code=code, defaults={
            "name": name, "valid_months": months, "statutory": statutory, "regulation": regulation,
            "has_rating": rating, "planned_task": task, "order": i * 10})
