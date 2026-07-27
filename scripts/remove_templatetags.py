import os

paths = [
    r"c:\Users\Kennedy\afraa_fuel_system\procurement\templatetags\procurement_tags.py.py",
    r"c:\Users\Kennedy\afraa_fuel_system\procurement\templatetags\dict_key",
]

for p in paths:
    try:
        os.remove(p)
        print('removed', p)
    except Exception as e:
        print('error', p, e)
