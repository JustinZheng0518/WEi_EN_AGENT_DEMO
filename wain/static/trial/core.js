/* Limited parameter recognition and a conservative offline snapshot demonstrator. No model calls. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WainTrial=value;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const EXAMPLES={
    normal:'我需要24V、每接点3A、10个普通接点另加PE，螺钉接线，导线1mm²，线缆外径8mm，环境25℃，1套。',
    crimp:'24V，每接点3A，10个普通接点另加PE，压接，导线1mm²，线缆外径8mm，环境25℃，2套，镀银端子。',
    overcurrent:'24V，每接点17A，10个普通接点另加PE，螺钉接线，导线1mm²，线缆外径8mm，25℃，1套。',
    missing:'24V，每接点3A，10个普通接点另加PE，压接，1套。'
  };
  const LABELS={male_insert:'公芯体',female_insert:'母芯体',hood:'电缆端外壳',panel_housing:'面板底座',cable_entry:'电缆接头',male_contacts:'公压接端子',female_contacts:'母压接端子'};
  function parse(text){
    const t=String(text).normalize('NFKC');const fields={};const messages=[];const unsupported=[];let ambiguous=false;
    const collect=(key,re,convert=Number)=>{const matches=[...t.matchAll(re)].map(m=>convert(m[1],m[2]));const values=[...new Set(matches)];if(values.length===1)fields[key]=values[0];if(values.length>1){fields[key]=null;messages.push('识别到多个'+({voltage:'电压',current:'电流',contacts:'接点数量',wire_mm2:'导线截面积',cable_diameter_mm:'线缆外径',ambient_c:'温度',quantity:'套数'}[key]||key)+'，请手动确认单一工况。');}};
    collect('voltage',/(?<![A-Za-z0-9.])(-?\d+(?:\.\d+)?)\s*(kV|V|伏特|伏)(?![A-Za-z])/gi,(n,u)=>Number(n)*(u.toLowerCase()==='kv'?1000:1));
    collect('current',/(?<![A-Za-z0-9.])(-?\d+(?:\.\d+)?)\s*(mA|A|安培|安)(?![A-Za-z])/gi,(n,u)=>Number(n)/(u.toLowerCase()==='ma'?1000:1));
    collect('contacts',/(\d+)\s*(?:个\s*)?(?:普通(?:接点|触点)|(?:signal|ordinary)\s+contacts?)/gi);
    if(fields.contacts===undefined){collect('contacts',/(\d+)\s*(?:个\s*)?(?:针|芯|接点|pins?|contacts?)(?![A-Za-z])/gi);if(fields.contacts!==undefined){ambiguous=true;messages.push('请确认针/芯数是普通接点数，保护接地 PE 另计。');}}
    collect('wire_mm2',/(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:mm\s*(?:2|\^2)|平方(?:毫米)?)/gi);
    collect('cable_diameter_mm',/(?:线缆(?:外径|直径)|电缆(?:外径|直径)|外径|cable\s*(?:diameter|OD)|\bOD)\s*(?:为|是|[:=])?\s*(-?\d+(?:\.\d+)?)\s*mm(?![\dA-Za-z])/gi);
    collect('ambient_c',/(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:°\s*C|摄氏度)/gi);
    collect('quantity',/(\d+)\s*(?:套|sets?|组)(?![A-Za-z])/gi);
    if(fields.current!==undefined&&!/(?:每(?:个)?(?:接点|触点|针)|每针|per\s*(?:contact|pin))/i.test(t)){ambiguous=true;messages.push('请确认电流为每接点电流，不是整组或整机电流。');}
    const terms=[['screw',/(?:螺钉|螺丝|screw)/i],['crimp',/(?:压接|crimp)/i],['spring',/(?:弹簧|spring)/i]].filter(([,re])=>re.test(t));
    if(terms.length===1)fields.termination=terms[0][0];else if(terms.length>1)messages.push('出现多种端接方式，请在参数中选择一种。');
    if(/(?:不要|不用|不使用|\bno\b|\bnot\b)\s*(?:螺钉|螺丝|压接|弹簧|screw|crimp|spring)/i.test(t)){fields.termination=null;messages.push('端接方式含否定表达，请手动选择需要的方式。');}
    if(/\b(?:M(?:8|12|15|17|23|27|40)(?:-[A-Z])?|HE|HD|HDD|HM|HVE|HQ)\b|HA-(?!010)\d{3}|Quick[- ]?in|快接/i.test(t))unsupported.push('本版仅支持 HA-010 的螺钉、压接和普通弹簧组件；描述涉及其他系列或端接形式。');
    const ips=[...t.matchAll(/IP\s*(\d{2}[A-Z]?)/gi)].map(m=>m[1]);if(ips.some(ip=>ip!=='65'))unsupported.push('描述要求的防护等级超出本版 IP65 组合试验范围。');
    if(/防爆|ATEX|IECEx|屏蔽|\bEMC\b|医用|食品级/i.test(t))unsupported.push('描述包含本版尚未验证的特殊要求，不能忽略后直接选型。');
    if(/\b(?:AC|DC)\b|交流|直流/i.test(t))messages.push('AC/DC 条件已在描述中保留；当前接口只作标称值初筛，电气标准仍需工程核对。');
    for(const m of t.matchAll(/\d+(?:\.\d+)?\s*(?:-|~|至|到|–)\s*\d+(?:\.\d+)?\s*(kV|V|mA|A|mm2|mm|°C)/gi)){
      const unit=m[1].toLowerCase();const keys=unit.includes('v')?['voltage']:unit.includes('a')?['current']:unit==='mm2'?['wire_mm2']:unit==='mm'?['cable_diameter_mm']:['ambient_c'];
      for(const key of keys)fields[key]=null;messages.push('范围值“'+m[0]+'”需要拆成明确的测试工况，请手动填写。');
    }
    if(/\bmV\b|\b(?:kA|MV)\b/.test(t))unsupported.push('描述包含当前规则未支持的单位，请换算后手动填写。');
    if(/顶进线|top\s*entry/i.test(t))fields.entry_direction='top';else if(/侧进线|side\s*entry/i.test(t))fields.entry_direction='side';
    if(/镀金|gold/i.test(t))fields.plating='gold';else if(/镀银|silver/i.test(t))fields.plating='silver';
    if(fields.quantity===undefined)messages.push('套数未明确，表单暂显示 1 套，请核对。');
    return {fields,messages,unsupported,ambiguous};
  }
  function validate(p){
    const errors=[];for(const [k,label] of [['voltage','工作电压'],['current','每接点电流'],['contacts','普通接点数量'],['quantity','连接套数']]){
      if(typeof p[k]!=='number'||!Number.isFinite(p[k])||p[k]<=0)errors.push('请填写有效的'+label+'。');
    }
    for(const k of ['contacts','quantity'])if(Number.isFinite(p[k])&&!Number.isInteger(p[k]))errors.push('接点数量和套数必须是整数。');
    for(const k of ['wire_mm2','cable_diameter_mm'])if(p[k]!==null&&(typeof p[k]!=='number'||!Number.isFinite(p[k])||p[k]<=0||p[k]>1000))errors.push('线径或外径必须是有效的正数。');
    if(p.ambient_c!==null&&(!Number.isFinite(p.ambient_c)||p.ambient_c< -273.15||p.ambient_c>1000))errors.push('请填写有效环境温度。');
    if(!['screw','crimp','spring'].includes(p.termination))errors.push('请选择端接方式。');
    if(p.quantity>10000||p.voltage>100000||p.current>100000||p.contacts>100)errors.push('输入超出试验接口范围。');
    return errors;
  }
  function offline(p,data){
    const errors=validate(p);if(errors.length)throw Error(errors.join('\n'));
    if(p.contacts!==10)throw Error('当前仅支持 10 个普通接点另加 PE；请使用支持范围内的工况。');
    if(!data||data.version!==1||!Array.isArray(data.products))throw Error('离线数据未准备好，请使用完整演示文件。');
    const products=data.products;const specs=(x,k)=>x?.specifications.filter(s=>s.parameter===k)||[];
    const number=(x,k)=>{const a=specs(x,k);return a.length===1&&a[0].value_number!==null?Number(a[0].value_number):null;};
    const text=(x,k)=>specs(x,k)[0]?.value_text;
    const byModel=m=>products.find(x=>x.model===m);
    const candidates=(category,value,lo,hi,gender)=>value===null?[]:products.filter(x=>x.category===category&&(!gender||x.gender===gender)&&number(x,lo)!==null&&number(x,hi)!==null&&number(x,lo)<=value&&number(x,hi)>=value).sort((a,b)=>(number(a,hi)-number(a,lo))-(number(b,hi)-number(b,lo))||a.id-b.id);
    const [m,f]={screw:['M','F'],crimp:['MC','FC'],spring:['MS','FS']}[p.termination];
    const chosen={male_insert:byModel('HA-010-'+m),female_insert:byModel('HA-010-'+f),hood:byModel('H10A-'+(p.entry_direction==='top'?'TE':'SE')+'-2B-M20'),panel_housing:byModel('H10A-BK-1L/SC'),cable_entry:candidates('cable_entry',p.cable_diameter_mm,'cable_diameter_min','cable_diameter_max').find(x=>text(x,'entry_thread_designation')==='M20x1.5')};
    if(p.termination==='crimp')for(const [role,gender] of [['male_contacts','male'],['female_contacts','female']])chosen[role]=candidates('contact',p.wire_mm2,'wire_cross_section_min','wire_cross_section_max',gender).find(x=>text(x,'plating')===p.plating);
    const checks=[];const add=(code,pass,message,pages=[])=>checks.push({code,status:pass===false?'failed':pass===true?'passed':'needs_confirmation',message,source_pages:pages});
    for(const [k,label] of [['wire_mm2','导线截面积'],['cable_diameter_mm','线缆外径'],['ambient_c','环境温度']])add('input_'+k,p[k]===null?null:true,label+(p[k]===null?'尚未填写。':'已提供。'));
    const bom=[];
    for(const [role,x] of Object.entries(chosen)){
      const qty=p.quantity*(role.endsWith('_contacts')?p.contacts:1);
      const row={role,label:LABELS[role],product_id:x?.id||null,model:x?.model||null,order_number:x?.order_number||null,quantity:qty,review_status:x?.review_status||null,source_pages:x?[x.global_page]:[]};bom.push(row);
      if(!x){const value=role==='cable_entry'?p.cable_diameter_mm:role.endsWith('_contacts')?p.wire_mm2:null;add('missing_'+role,value===null?null:false,LABELS[role]+'未选定，需要明确条件及适用产品。');continue;}
      add('review_'+role,null,LABELS[role]+'为真实转录候选，仍需独立审核与适配核对。',[x.global_page]);
      for(const [key,value,unit] of [['rated_voltage',p.voltage,'V'],['rated_current',p.current,'A']])if(x.category==='insert'||x.category==='contact'&&key==='rated_current'){
        const limit=number(x,key);add(role+'_'+key,limit!==null&&value>limit?false:null,LABELS[role]+(limit===null?'额定参数待核对。':'要求 '+value+unit+'，目录标称 '+limit+unit+'；仍需核对适用条件。'),[x.global_page]);
      }
      if(['insert','contact','cable_entry'].includes(x.category)){
        const gland=x.category==='cable_entry',value=gland?p.cable_diameter_mm:p.wire_mm2,lo=number(x,gland?'cable_diameter_min':'wire_cross_section_min'),hi=number(x,gland?'cable_diameter_max':'wire_cross_section_max');
        add('range_'+role,value!==null&&lo!==null&&hi!==null&&(value<lo||value>hi)?false:null,LABELS[role]+'适用'+(gland?'外径':'线径')+'：'+(lo===null||hi===null?'待核对':lo+'–'+hi+(gland?'mm':'mm²'))+'。',[x.global_page]);
      }
      if(x.category==='insert'){
        const lo=number(x,'limiting_temperature_min'),hi=number(x,'limiting_temperature_max');
        add('temperature_'+role,p.ambient_c!==null&&lo!==null&&hi!==null&&(p.ambient_c<lo||p.ambient_c>hi)?false:null,'材料极限温度与实际带载降额需要分别核对。',specs(x,'limiting_temperature_min').map(s=>s.global_page));
      }
      const pack=number(x,'standard_pack_quantity');if(pack>0){row.suggested_purchase_quantity=Math.ceil(qty/pack)*pack;row.pack_quantity_reviewed=false;}
    }
    for(const [code,label] of [['derating','实际工况下降额'],['mechanical_sealing','螺纹、密封、锁扣与完整附件'],['pe_termination','PE 接地结构及数量'],['pinout_mounting','针位、防呆和安装空间']])add('assessment_'+code,null,label+'仍需有来源的工程核对。');
    if(p.termination==='crimp')add('assembly_tools',null,'需按端子、线径和厂家工艺选择压接及退针工具；工具不计入成品 BOM。');
    add('offline_scope',null,'离线版只演示基础初筛和数量；没有执行服务端的全部依赖与工程记录检查。');
    return {status:checks.some(x=>x.status==='failed')?'failed':'needs_confirmation',can_finalize:false,bom,checks,scope:{request:p,products:Object.fromEntries(Object.entries(chosen).map(([k,x])=>[k,x?.id||null]))},notice:'离线样板数据初筛，不是完整工程校验；最终状态始终不作为批准。',validation_level:'offline_basic_only',assumptions:{entry_direction:p.entry_direction,contact_plating:p.plating}};
  }
  return {EXAMPLES,LABELS,parse,validate,offline};
});
