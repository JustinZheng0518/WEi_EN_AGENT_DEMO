const {test}=require('node:test');const assert=require('node:assert/strict');
const Core=require('../wain/static/trial/core.js');
test('explicit Chinese example has the expected units and no ambiguity',()=>{
  const r=Core.parse(Core.EXAMPLES.normal);
  assert.equal(r.fields.voltage,24);assert.equal(r.fields.current,3);assert.equal(r.fields.contacts,10);
  assert.equal(r.fields.wire_mm2,1);assert.equal(r.fields.cable_diameter_mm,8);assert.equal(r.fields.ambient_c,25);
  assert.equal(r.fields.termination,'screw');assert.equal(r.ambiguous,false);assert.deepEqual(r.unsupported,[]);
});
test('English units, full-width numbers and negative temperature are recognized',()=>{
  const r=Core.parse('２４Ｖ, 3000mA per contact, 10 ordinary contacts + PE, crimp, 1.5mm2 wire, cable diameter 8mm, -20°C, 2 sets');
  assert.equal(r.fields.voltage,24);assert.equal(r.fields.current,3);assert.equal(r.fields.ambient_c,-20);
  assert.equal(r.fields.quantity,2);assert.equal(r.fields.contacts,10);
});
test('ambiguous pin and current language requires explicit confirmation',()=>{
  assert.equal(Core.parse('24V 3A 10针 螺钉').ambiguous,true);
});
test('range and conflicting values are not reduced to the first number',()=>{
  assert.equal(Core.parse('24V或48V').fields.voltage,null);
  assert.equal(Core.parse('3-5A').fields.current,null);
  assert.equal(Core.parse('线径0.5-2.5mm2').fields.wire_mm2,null);
});
test('unsupported series, protection and special requirements remain visible',()=>{
  assert(Core.parse('M12 8针 24V').unsupported.length);
  assert(Core.parse('HA-003 3针').unsupported.length);
  assert(Core.parse('HA-010 24V IP68 防爆').unsupported.length>=2);
});
test('negation and multiple terminations do not pick a misleading mode',()=>{
  assert.equal(Core.parse('不要螺钉').fields.termination,null);
  assert.equal(Core.parse('螺钉或压接').fields.termination,undefined);
});
test('missing optional dimensions and basic field validation are explicit',()=>{
  const r=Core.parse(Core.EXAMPLES.missing);
  assert.equal(r.fields.wire_mm2,undefined);assert.equal(r.fields.cable_diameter_mm,undefined);
  assert(Core.validate({voltage:24,current:NaN,contacts:10,termination:'screw',quantity:1,wire_mm2:null,cable_diameter_mm:null,ambient_c:null}).length);
});
