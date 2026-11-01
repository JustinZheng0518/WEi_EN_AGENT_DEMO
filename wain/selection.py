"""HA-010 connector component pilot. Unknown evidence blocks finalization."""
import hashlib
import json
import math
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,PositiveInt,field_validator

ROLES={'male_insert':('insert','male'),'female_insert':('insert','female'),
       'hood':('hood',None),'panel_housing':('housing',None),'cable_entry':('cable_entry',None),
       'male_contacts':('contact','male'),'female_contacts':('contact','female')}
LABELS={'male_insert':'公芯体','female_insert':'母芯体','hood':'电缆端外壳','panel_housing':'面板底座',
        'cable_entry':'电缆接头','male_contacts':'公压接端子','female_contacts':'母压接端子'}

class SelectionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    voltage:float=Field(gt=0,le=100000)
    current:float=Field(gt=0,le=100000)
    contacts:int=Field(default=10,ge=1,le=100)
    termination:Literal['screw','crimp','spring']='screw'
    wire_mm2:float|None=Field(None,gt=0,le=1000)
    cable_diameter_mm:float|None=Field(None,gt=0,le=1000)
    ambient_c:float|None=Field(None,ge=-273.15,le=1000)
    quantity:int=Field(default=1,ge=1,le=10000)
    entry_direction:Literal['side','top']='side'
    plating:Literal['silver','gold']='silver'
    components:dict[str,PositiveInt|None]=Field(default_factory=dict)

    @field_validator('wire_mm2','cable_diameter_mm','ambient_c',mode='before')
    @classmethod
    def na_input(cls,value):
        return None if isinstance(value,str) and value.strip().upper()=='NA' else value

    @field_validator('components')
    @classmethod
    def valid_roles(cls,value):
        if set(value)-set(ROLES): raise ValueError('Unknown BOM component role')
        return value

def select(conn,request):
    checks=[]; bom=[]
    def check(code,passed,message,pages=()):
        checks.append({'code':code,'status':'needs_confirmation' if passed is None else 'passed' if passed else 'failed',
                       'message':message,'source_pages':list(pages)})
    check('scope',request.contacts==10,'本试验范围为 HA-010：10 个普通接点另加 PE，电缆到面板连接器组件。',[76])
    for name,value,label in [('wire',request.wire_mm2,'导线截面积'),('diameter',request.cable_diameter_mm,'线缆外径'),('ambient',request.ambient_c,'环境温度')]:
        check('input_'+name,True if value is not None else None,label+('已提供。' if value is not None else 'NA，需要补充。'))
    def by_model(model):
        row=conn.execute('SELECT id FROM products WHERE model=%s ORDER BY id LIMIT 1',(model,)).fetchone()
        return row['id'] if row else None
    suffix={'screw':('M','F'),'crimp':('MC','FC'),'spring':('MS','FS')}[request.termination]
    chosen={'male_insert':by_model('HA-010-'+suffix[0]),'female_insert':by_model('HA-010-'+suffix[1]),
        'hood':by_model('H10A-'+('SE' if request.entry_direction=='side' else 'TE')+'-2B-M20'),
        'panel_housing':by_model('H10A-BK-1L/SC'),'cable_entry':None}
    # Default contact finish is explicit in request; no missing wire size is guessed.
    for category,input_value,min_key,max_key,roles in [
        ('cable_entry',request.cable_diameter_mm,'cable_diameter_min','cable_diameter_max',['cable_entry']),
        ('contact',request.wire_mm2,'wire_cross_section_min','wire_cross_section_max',
         ['male_contacts','female_contacts'] if request.termination=='crimp' else [])]:
        for role in roles:
            chosen.setdefault(role,None)
            if input_value is None: continue
            gender=ROLES[role][1]
            rows=conn.execute('''SELECT p.id FROM products p JOIN product_specifications lo ON lo.product_id=p.id
                JOIN product_specifications hi ON hi.product_id=p.id WHERE p.category=%s
                AND lo.parameter=%s AND hi.parameter=%s AND lo.value_number<=%s AND hi.value_number>=%s
                AND (%s::text IS NULL OR p.gender=%s)
                AND (%s='cable_entry' OR EXISTS(SELECT 1 FROM product_specifications f WHERE f.product_id=p.id
                    AND f.parameter='plating' AND f.value_text=%s))
                AND (%s='contact' OR EXISTS(SELECT 1 FROM product_specifications t WHERE t.product_id=p.id
                    AND t.parameter='entry_thread_designation' AND t.value_text='M20x1.5'))
                ORDER BY (hi.value_number-lo.value_number),p.id LIMIT 1''',
                (category,min_key,max_key,input_value,input_value,gender,gender,category,request.plating,category)).fetchall()
            chosen[role]=rows[0]['id'] if rows else None
    for role,pid in request.components.items():
        if role in chosen: chosen[role]=pid
        else: check('unexpected_'+role,False,'本端接方式不应包含 '+LABELS[role]+'。')
    facts={}
    def spec_ok(spec): return spec['value_state']=='known' and spec['review_status']=='reviewed' and spec['evidence_status']=='reviewed'
    for role,pid in chosen.items():
        p=conn.execute('''SELECT p.*,e.review_status AS evidence_status,pg.global_page FROM products p
            JOIN evidence e ON e.id=p.evidence_id JOIN pages pg ON pg.id=e.page_id WHERE p.id=%s''',(pid,)).fetchone() if pid else None
        required=request.quantity*(request.contacts if role.endswith('_contacts') else 1)
        item={'role':role,'label':LABELS[role],'product_id':pid,'model':p['model'] if p else None,
              'order_number':p['order_number'] if p else None,'quantity':required,
              'review_status':p['review_status'] if p else None,'source_pages':[p['global_page']] if p else []}
        bom.append(item)
        if not p:
            known_input=request.cable_diameter_mm if role=='cable_entry' else request.wire_mm2 if role.endswith('_contacts') else None
            check('component_'+role,False if known_input is not None or role in request.components or pid is not None else None,LABELS[role]+'未选定；需要有效产品和适用范围。')
            continue
        values=conn.execute('''SELECT s.*,e.review_status AS evidence_status,pg.global_page FROM product_specifications s
            JOIN evidence e ON e.id=s.evidence_id JOIN pages pg ON pg.id=e.page_id WHERE s.product_id=%s''',(pid,)).fetchall()
        specs={}
        for s in values: specs.setdefault(s['parameter'],[]).append(s)
        facts[role]=(p,specs)
        for s in values:
            if s['value_state']=='NA':
                check('na_'+role+'_'+s['parameter'],None,
                    LABELS[role]+'的 '+s['parameter']+' 明确NA，需确认适用条件及依据：'+s['state_reason'],[s['global_page']])
        required_specs={'hood':['entry_thread_designation','locking_geometry','entry_direction','ip_rating'],
            'panel_housing':['locking_variant','mounting','ip_rating'],
            'cable_entry':['entry_thread_designation','thread_length','sealing','ip_rating']}.get(role,[])
        for key in required_specs:
            source=specs.get(key,[])
            check('parameter_'+role+'_'+key,True if len(source)==1 and spec_ok(source[0]) else None,
                LABELS[role]+'参数 '+key+' 需单独审核。',[s['global_page'] for s in source])
        if role.endswith('_insert'):
            lo=specs.get('limiting_temperature_min',[]);hi=specs.get('limiting_temperature_max',[])
            temp=None
            if request.ambient_c is not None and len(lo)==len(hi)==1 and lo[0]['unit']==hi[0]['unit']=='degC' and lo[0]['value_number'] is not None and hi[0]['value_number'] is not None:
                within=float(lo[0]['value_number'])<=request.ambient_c<=float(hi[0]['value_number'])
                temp=False if not within else True if spec_ok(lo[0]) and spec_ok(hi[0]) else None
            check('temperature_'+role,temp,LABELS[role]+'必须满足材料极限温度，且仍需另核对带载降额。',[73])
        category,gender=ROLES[role]
        valid=p['category']==category and (gender is None or p['gender']==gender)
        if role.endswith('_insert'):
            valid=valid and p['contact_count']==request.contacts and p['pe_contacts']==1 and p['termination']==request.termination and p['model'].startswith('HA-010-')
        if role in {'hood','panel_housing'}: valid=valid and p['housing_size']=='10A'
        check('type_'+role,valid,LABELS[role]+'的类别、接点及端接要求'+('相符。' if valid else '不相符。'),[p['global_page']])
        identity=p['review_status']=='reviewed' and p['evidence_status']=='reviewed'
        check('review_'+role,True if identity else None,LABELS[role]+('身份与来源已确认。' if identity else '身份或来源仍待审核。'),[p['global_page']])
        packs=specs.get('standard_pack_quantity',[])
        if len(packs)==1 and packs[0]['unit']=='pcs' and packs[0]['value_number'] and packs[0]['value_number']>0:
            pack=float(packs[0]['value_number']);item['suggested_purchase_quantity']=math.ceil(required/pack)*pack
            item['pack_quantity_reviewed']=spec_ok(packs[0])
            check('pack_'+role,True if spec_ok(packs[0]) else None,LABELS[role]+'包装数量'+('已审核。' if spec_ok(packs[0]) else '仍待审核，采购取整仅供核对。'),[packs[0]['global_page']])
        else: check('pack_'+role,None,LABELS[role]+'缺少唯一有效包装数据。')
        for parameter,required_value,unit in [('rated_voltage',request.voltage,'V'),('rated_current',request.current,'A')]:
            if category not in {'insert','contact'} or (category=='contact' and parameter=='rated_voltage'): continue
            candidates=[s for s in specs.get(parameter,[]) if s['unit']==unit and s['value_number'] is not None and s['value_number']>0]
            if len(candidates)!=1:
                check(role+'_'+parameter,None,LABELS[role]+'的额定参数缺失、单位不符或存在多个条件值。');continue
            s=candidates[0];within=required_value<=float(s['value_number'])
            check(role+'_'+parameter,False if not within else True if spec_ok(s) else None,
                LABELS[role]+f'要求 {required_value:g}{unit}，目录候选额定值 {s["value_number"]}{unit}；仍需满足适用条件。',[s['global_page']])
        range_keys=('cable_diameter_min','cable_diameter_max','mm',request.cable_diameter_mm) if role=='cable_entry' else ('wire_cross_section_min','wire_cross_section_max','mm2',request.wire_mm2)
        if category in {'insert','contact','cable_entry'}:
            lo,hi,u,value=range_keys
            low=specs.get(lo,[]);high=specs.get(hi,[])
            if value is None or len(low)!=1 or len(high)!=1 or low[0]['unit']!=u or high[0]['unit']!=u or low[0]['value_state']!='known' or high[0]['value_state']!='known':
                check('range_'+role,None,LABELS[role]+'需要有效线径/外径及有来源的适用范围。')
            else:
                a=low[0]['value_number'];b=high[0]['value_number']
                in_range=a is not None and b is not None and 0<float(a)<=value<=float(b)
                check('range_'+role,False if not in_range else True if spec_ok(low[0]) and spec_ok(high[0]) else None,
                    LABELS[role]+f'输入 {value:g}{u}；目录范围 {a}–{b}{u}。',[low[0]['global_page'],high[0]['global_page']])
    edges=[('male_insert','female_insert','mates_with'),('male_insert','hood','uses_housing'),
        ('female_insert','panel_housing','uses_housing'),('hood','panel_housing','mates_with'),
        ('hood','cable_entry','requires_accessory')]
    if request.termination=='crimp': edges.extend([('male_insert','male_contacts','uses_contact'),('female_insert','female_contacts','uses_contact')])
    for source,target,relation in edges:
        rows=conn.execute('''SELECT r.*,e.review_status AS evidence_status,pg.global_page FROM product_relations r
            JOIN evidence e ON e.id=r.evidence_id JOIN pages pg ON pg.id=e.page_id
            WHERE r.source_product_id=%s AND r.target_product_id=%s AND r.relation=%s''',
            (chosen.get(source),chosen.get(target),relation)).fetchall()
        # Unknown conditions never become true merely because a relationship was reviewed.
        verified=any(r['review_status']=='reviewed' and r['evidence_status']=='reviewed' and
            (not r['conditions'] or r['conditions']=={'requires_wire_gauge_check':True}) for r in rows)
        conflict=any(r['review_status']=='conflict' for r in rows)
        check('relation_'+source+'_'+target,False if conflict else True if verified else None,
            LABELS[source]+' → '+LABELS[target]+('：适配关系存在冲突。' if conflict else '：有已审核适配依据。' if verified else '：缺少已审核且条件明确的适配依据。'),
            sorted({r['global_page'] for r in rows}))
    # Inspect every mandatory accessory edge, not just the fixed pilot roles. Missing dependencies
    # must block approval even when all familiar major components are present.
    selected_ids={v for v in chosen.values() if v is not None}
    scanned=set();pending=list(selected_ids)
    while pending:
        source_id=pending.pop()
        if source_id in scanned: continue
        scanned.add(source_id)
        dependencies=conn.execute('''SELECT r.*,t.model,t.order_number,t.review_status AS product_status,
            e.review_status AS evidence_status,p.global_page FROM product_relations r
            JOIN products t ON t.id=r.target_product_id JOIN evidence e ON e.id=r.evidence_id
            JOIN pages p ON p.id=e.page_id WHERE r.source_product_id=%s AND r.relation='requires_accessory' ''',(source_id,)).fetchall()
        for dep in dependencies:
            target_id=dep['target_product_id']
            if target_id in selected_ids: continue
            pending.append(target_id)
            check('dependency_'+str(dep['id']),None,
                '需要另核对必需附件 '+dep['model']+' 及数量、来源和适用条件；当前组合不能确认完整。',[dep['global_page']])
            if not any(item['product_id']==target_id for item in bom):
                bom.append({'role':'accessory_'+str(target_id),'label':'额外必需附件','product_id':target_id,
                    'model':dep['model'],'order_number':dep['order_number'],'quantity':None,
                    'review_status':dep['product_status'],'source_pages':[dep['global_page']]})
    scope={'request':request.model_dump(exclude={'components'}),'products':chosen}
    assessment_codes={
        'derating':('降额与实际工况',{'capacity_a','voltage_v'}),
        'mechanical_sealing':('螺纹、密封、锁扣与附件完整性',{'thread_compatible','thread_engagement','seal_complete','locking_compatible','ip65_verified','all_accessories_accounted_for'}),
        'pe_termination':('PE 接地结构与端子数量',{'pe_complete'}),
        'pinout_mounting':('针位、防呆和安装空间',{'pinout_verified','polarization_verified','mounting_clearance'})}
    from psycopg.types.json import Jsonb
    for code,(label,keys) in assessment_codes.items():
        rows=conn.execute('''SELECT a.*,e.review_status AS evidence_status,p.global_page FROM assembly_assessments a
            JOIN evidence e ON e.id=a.evidence_id JOIN pages p ON p.id=e.page_id
            WHERE a.check_code=%s AND a.scope=%s ORDER BY a.id DESC''',(code,Jsonb(scope))).fetchall()
        latest=rows[0] if rows else None
        approved=latest if latest and latest['review_status']=='reviewed' and latest['evidence_status']=='reviewed' else None
        ok=False if latest and latest['review_status']=='conflict' else None
        if approved:
            f=approved['findings']
            if code=='derating':
                ok=all(type(f.get(k)) in (int,float) and math.isfinite(f[k]) and f[k]>0 for k in keys)
                ok=ok and f['capacity_a']>=request.current and f['voltage_v']>=request.voltage
            else: ok=all(f.get(k) is True for k in keys)
        check('assessment_'+code,ok,label+('已有与本组合和工况完全对应的审核结论。' if ok else '需要有来源的工程核对；不能由模型猜测。'),
            [approved['global_page']] if approved else [])
    if any(v is None for v in chosen.values()): check('closure',None,'仍有必需组件未选定。')
    status='failed' if any(c['status']=='failed' for c in checks) else 'needs_confirmation' if any(c['status']=='needs_confirmation' for c in checks) else 'passed'
    return {'status':status,'can_finalize':status=='passed','scope':scope,'bom':bom,'checks':checks,
        'scope_hash':hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest(),
        'notice':'电缆到面板连接器组件试验：线缆由用户提供，普通接点与 PE 分开核对。标称参数筛选不代替降额、密封和装配验证。',
        'assumptions':{'entry_direction':request.entry_direction,'contact_plating':request.plating,'target_ip':'IP65 when assembled and verified'},
        'assembly_tools':['需按端子、线径和厂家工艺选择压接及退针工具；不计入成品 BOM。'] if request.termination=='crimp' else []}
