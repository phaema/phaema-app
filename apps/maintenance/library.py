# SPDX-License-Identifier: AGPL-3.0-or-later
"""PHAEMA's open library of planned maintenance tasks.

A starting point written for PHAEMA, not a copy of any commercial schedule. Frequencies are common
practice for commercial premises; check them against the council's own risk assessments, written
schemes of examination and the manufacturer's instructions.
"""
from .models import Category

C = Category
RRO = "Regulatory Reform (Fire Safety) Order 2005"

# code, task, category, every (months), statutory, law or standard
TASKS = [
    ("gas_safety", "Gas safety check and service of gas appliances", C.MECHANICAL, 12, True,
     "Gas Safety (Installation and Use) Regulations 1998"),
    ("eicr", "Fixed electrical installation inspection (EICR)", C.ELECTRICAL, 60, True,
     "Electricity at Work Regulations 1989; BS 7671"),
    ("fire_alarm", "Fire alarm service and inspection", C.FIRE, 6, True, f"{RRO}; BS 5839-1"),
    ("emergency_lighting", "Emergency lighting full-duration test", C.FIRE, 12, True, f"{RRO}; BS 5266-1"),
    ("extinguishers", "Fire extinguisher service", C.FIRE, 12, True, f"{RRO}; BS 5306-3"),
    ("fra_review", "Fire risk assessment review (common parts)", C.FIRE, 12, True, RRO),
    ("fire_doors", "Fire door inspection (common parts)", C.FIRE, 6, True, RRO),
    ("risers", "Dry or wet riser test", C.FIRE, 6, True, f"{RRO}; BS 9990"),
    ("legionella_ra", "Legionella risk assessment review", C.MECHANICAL, 24, True,
     "Health and Safety at Work etc. Act 1974; HSE ACoP L8"),
    ("water_temps", "Water temperature monitoring", C.MECHANICAL, 1, True, "HSE ACoP L8"),
    ("asbestos", "Asbestos re-inspection and management plan review", C.STRUCTURE, 12, True,
     "Control of Asbestos Regulations 2012, regulation 4"),
    ("lift_exam", "Passenger lift thorough examination", C.LIFT, 6, True,
     "Lifting Operations and Lifting Equipment Regulations 1998"),
    ("lift_service", "Lift maintenance visit", C.LIFT, 3, False, "Manufacturer's instructions"),
    ("pressure", "Pressure system examination (to the written scheme)", C.MECHANICAL, 12, True,
     "Pressure Systems Safety Regulations 2000"),
    ("aircon_tm44", "Air conditioning energy inspection (systems over 12 kW)", C.MECHANICAL, 60, True,
     "Energy Performance of Buildings (England and Wales) Regulations 2012"),
    ("roof_anchors", "Roof anchors and fall arrest inspection", C.ROOF, 12, True,
     "Work at Height Regulations 2005; BS 7883"),
    ("boiler_service", "Boiler and heating plant service", C.MECHANICAL, 12, False, "Manufacturer's instructions"),
    ("lightning", "Lightning protection test", C.ELECTRICAL, 12, False, "BS EN 62305"),
    ("auto_doors", "Automatic doors and gates service", C.EXTERNAL, 6, False, "BS EN 16005"),
    ("roof_gutters", "Roof inspection and gutter clearance", C.ROOF, 12, False, ""),
    ("drains", "Drainage inspection and jetting", C.EXTERNAL_WORKS, 24, False, ""),
    ("condition_survey", "Condition survey", C.OTHER, 60, False, "RICS guidance"),
]
BY_CODE = {t[0]: t for t in TASKS}
