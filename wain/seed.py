"""Small visually transcribed pilot; all facts remain pending independent review."""
from psycopg.types.json import Jsonb


def seed(conn):
    families={}
    for code,name,category in [('HA','The slim inserts','insert'),('CE','16A crimp contacts','contact'),('TOOLS','Assembly tools','tool')]:
        families[code]=conn.execute('''INSERT INTO product_families(code,name,category) VALUES(%s,%s,%s)
            ON CONFLICT(code) DO UPDATE SET name=excluded.name RETURNING id''',(code,name,category)).fetchone()['id']

    def evidence(key,page,region,quote):
        return conn.execute('''INSERT INTO evidence(evidence_key,page_id,region,quotation,method)
            VALUES(%s,(SELECT id FROM pages WHERE global_page=%s),%s,%s,'visual_transcription')
            ON CONFLICT(evidence_key) DO UPDATE SET evidence_key=excluded.evidence_key RETURNING id''',
            (key,page,Jsonb(region),quote)).fetchone()['id']

    technical=evidence('ha-technical-01-02',73,[.08,.17,.49,.74],
        'HA-010/HA-016; Rated current 16A; Rated voltage 250V; Pollution degree 3; '
        'The current carrying is limited by maximum temperature of materials for inserts and contacts including terminals.')
    contacts=evidence('ha-contacts-01-04',76,[.07,.54,.94,.80],
        'Crimp contacts 16A; silver plated; gold plated; Remark: SPQ is 100pcs')
    tools=evidence('ha-tools-01-04',76,[.07,.80,.94,.94],
        'Crimping tool TL02G 198 001 001 0011; Contact removal tool TL01 198 001 000 0002; '
        'Wire gauge: 0.14-0.37mm² please select TL02 Crimping tool.')
    ids={}

    def product(model,order,family,category,gender,termination,count,pe,size,ev):
        # Never overwrite a subsequently reviewed row on a repeat import.
        row=conn.execute('''INSERT INTO products(family_id,model,order_number,category,gender,termination,
            contact_count,pe_contacts,housing_size,evidence_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(order_number) DO UPDATE SET order_number=excluded.order_number RETURNING id''',
            (families[family],model,order.replace(' ',''),category,gender,termination,count,pe,size,ev)).fetchone()
        ids[model]=row['id']
        return row['id']

    def spec(pid,key,number,unit,ev,conditions=None,text=None):
        conn.execute('''INSERT INTO product_specifications(product_id,parameter,value_number,value_text,unit,conditions,evidence_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,parameter,conditions) DO NOTHING''',
            (pid,key,number,text,unit,Jsonb(conditions or {}),ev))

    for count,page,size in [(10,76,'10A'),(16,77,'16A')]:
        ev=evidence(f'ha-{count}-ordering',page,[.27,.14,.68,.53],
            f'HA-{count:03d} The slim inserts; 250V 16A {count}+PE; Hoods/Housings: size {size}; '
            'Crimp terminal: Order crimp contacts separately')
        conn.execute('UPDATE pages SET printed_page=%s WHERE global_page=%s',('01-04' if page==76 else '01-05',page))
        rows=[('M','011','0001','screw','male'),('F','021','0001','screw','female'),
              ('M/B','011','0503' if count==10 else '0505','screw','male'),
              ('F/B','021','0503' if count==10 else '0505','screw','female'),
              ('MC','010','0001','crimp','male'),('FC','020','0001','crimp','female')]
        if count==10:
            rows.extend([('MS','012','0001','spring','male'),('FS','022','0001','spring','female')])
        for suffix,middle,end,termination,gender in rows:
            pid=product(f'HA-{count:03d}-{suffix}',f'121 {count:03d} {middle} {end}',
                'HA','insert',gender,termination,count,1,size,ev)
            cond={'standard':'EN 61984','pollution_degree':3,'requires_derating_check':True}
            spec(pid,'rated_current',16,'A',technical,cond)
            spec(pid,'rated_voltage',250,'V',technical,cond)
            spec(pid,'standard_pack_quantity',5,'pcs',ev)
            spec(pid,'housing_catalog_reference',None,None,ev,text='15-17 to 15-18.1' if count==10 else '15-19 to 15-20')

    gauges=[('0.37','0301'),('0.50','0401'),('0.75','0601'),('1.0','0801'),
            ('1.5','0901'),('2.5','1001'),('3.0','1101'),('4.0','1201')]
    for plating,mp,fp,mc,fc in [('silver','CESM','CESF','110','120'),('gold','CEGM','CEGF','210','220')]:
        for gauge,ending in gauges:
            for prefix,code,gender in [(mp,mc,'male'),(fp,fc,'female')]:
                pid=product(f'{prefix}-{gauge}',f'101 019 {code} {ending}',
                    'CE','contact',gender,'crimp',None,None,None,contacts)
                spec(pid,'rated_current',16,'A',contacts,{'requires_derating_check':True})
                spec(pid,'plating',None,None,contacts,text=plating)
                spec(pid,'wire_cross_section_min',.14 if gauge=='0.37' else float(gauge),'mm2',contacts)
                spec(pid,'wire_cross_section_max',float(gauge),'mm2',contacts)
                spec(pid,'standard_pack_quantity',100,'pcs',contacts)
                # Source lists these contacts on the same insert page. Applicability remains pending review.
                for count in [10,16]:
                    source=ids[f'HA-{count:03d}-'+('MC' if gender=='male' else 'FC')]
                    conn.execute('''INSERT INTO product_relations(source_product_id,target_product_id,relation,conditions,evidence_id)
                        VALUES(%s,%s,'uses_contact',%s,%s) ON CONFLICT DO NOTHING''',
                        (source,pid,Jsonb({'requires_wire_gauge_check':True}),contacts))
    for model,order in [('TL02G','198 001 001 0011'),('TL01','198 001 000 0002')]:
        product(model,order,'TOOLS','tool','none',None,None,None,None,tools)
    conn.execute("UPDATE pages SET printed_page='01-02' WHERE global_page=73")
    template=conn.execute('''INSERT INTO assembly_templates(code,description)
        VALUES('rectangular-cable-panel','Pilot cable-to-panel assembly; not approved for final BOM generation')
        ON CONFLICT(code) DO UPDATE SET code=excluded.code RETURNING id''').fetchone()['id']
    for role,condition,quantity in [
        ('male_insert',{},'one per connection'),('female_insert',{},'one per connection'),
        ('male_contacts',{'termination':'crimp'},'one per populated signal/power cavity; PE construction must be checked'),
        ('female_contacts',{'termination':'crimp'},'one per populated signal/power cavity; PE construction must be checked'),
        ('hood',{},'installation-dependent'),('panel_housing',{},'installation-dependent'),
        ('cable_entry',{},'depends on cable diameter, entry thread and sealing requirements')]:
        conn.execute('''INSERT INTO assembly_requirements(template_id,role,required,condition,quantity_rule)
            VALUES(%s,%s,true,%s,%s) ON CONFLICT DO NOTHING''',(template,role,Jsonb(condition),quantity))
    conn.execute('''INSERT INTO compatibility_rules(code,description,rule,evidence_id)
        VALUES('ha-derating','Full electrical validation requires ambient temperature and wire conditions',%s,%s)
        ON CONFLICT DO NOTHING''',(Jsonb({'required_context':['ambient_temperature','wire_cross_section','loaded_contacts'],
            'automatic_approval':False}),technical))
    return {'pilot_products':len(ids),'review_status':'pending','source_pages':[73,76,77]}
