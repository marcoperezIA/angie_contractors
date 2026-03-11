import csv

with open('companies_glassdor_indeed.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

# Empresas gigantes/corporativas (no necesitan nearshore)
giants = ['apple','oracle','netflix','salesforce','amazon','fedex','verizon',
          'chanel','burberry','madewell','cvs','sherwin','general motors',
          'medtronic','disney','universal music','michaels store','paychex',
          'darktrace','cornerstone','xometry','nielsen','barilla','fiji water',
          'speedo','harman','toast inc','ramp ','kelly ','tito']

# Universidades, hospitales, gobierno
inst = ['university','college','city of ','county of','hospital','keck medicine',
        'arizona state','l.a. care','health plan','community clinic','botanic garden',
        'ellison medical','hope the mission','vista del mar','pacific hospital']

# Retail puro
retail = ["dick's sporting",'sally beauty','cosmoprof','topgolf callaway','wireless vision']

# Titulos que NO son SDR/outbound sales
bad_titles = ['coordinator','dispatcher','pbx operator','scheduler','authorization',
              'patient access','operations manager','facility manager','plant manager',
              'project manager','program manager','marketing manager','quality engineering',
              'creative manager','ecommerce','educator','clinical','mortgage','benefit',
              'support coordinator','client services','staff assistant','correspondence clerk',
              'category specialist','co-founder','vice president','director of oper',
              'director, sales prog','general manager','regional supervisor',
              'assistant manager','store director','guest experience','senior manager']

# Misc que no sirven
misc = ['sara simpson','tutor me','solomon page','endeavor bank','pronto insurance',
        'state farm','farmers insurance','pocketbook','skyryse','global group',
        'fenner','lucky strike','gsi ','arc ','wonderful company','on location',
        'custom goods','ampam','action property','wolf & shepherd','dancar',
        'o2 technologies','rollins','crystal stairs','medpoint','pennymac',
        'alignment health','ephonamation','clever care','south coast botanic',
        'roypow','sea dwelling','cameo beverly','forest lawn']

good = []
removed = []
for row in rows:
    c = row['company'].lower()
    t = row['job_title'].lower()
    skip = False
    for lst in [giants, inst, retail, misc]:
        for kw in lst:
            if kw in c:
                skip = True
    for bt in bad_titles:
        if bt in t:
            skip = True
    if skip:
        removed.append(row)
    else:
        good.append(row)

FN = ['company','phone','website','job_title','location','description','source','job_url']
with open('hiring_filtered_services.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=FN)
    w.writeheader()
    for r in good:
        w.writerow(r)

print(f"\nEmpresas que SI sirven: {len(good)}")
print(f"Eliminadas: {len(removed)}\n")
print("="*60)
print("  ESTAS SI SIRVEN (service companies buscando SDR/sales):")
print("="*60)
for i, r in enumerate(good):
    print(f"  {i+1}. {r['company']} | {r['job_title']}")

print(f"\n{'='*60}")
print("  ELIMINADAS:")
print("="*60)
for i, r in enumerate(removed):
    print(f"  x  {r['company']} | {r['job_title']}")
