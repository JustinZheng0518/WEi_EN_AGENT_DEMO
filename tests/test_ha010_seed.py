from wain.ha010_seed import seed_ha010
from wain.service import stats
from test_database import db

def companion_pages(db):
    for number in [57,445,469,470,1401]:
        did=db.execute('''INSERT INTO documents(sha256,filename,source_path,page_start,page_end,page_count)
            VALUES(%s,'fixture.pdf','/nonexistent',%s,%s,1) RETURNING id''',(str(number).zfill(64),number,number)).fetchone()['id']
        db.execute('INSERT INTO pages(document_id,local_page,global_page,width_pt,height_pt) VALUES(%s,1,%s,595,842)',(did,number))

def test_companion_import_is_idempotent_and_preserves_unknowns(db):
    companion_pages(db)
    seed_ha010(db); before=stats(db); seed_ha010(db); after=stats(db)
    assert before==after
    assert after['products']==54
    assert after['product_review']=={'pending':54}
    gland=db.execute("SELECT id FROM products WHERE model='WNA-M20(D6-12)'").fetchone()['id']
    specs={r['parameter']:r for r in db.execute('SELECT * FROM product_specifications WHERE product_id=%s',(gland,)).fetchall()}
    assert specs['cable_diameter_min']['value_number']==6
    assert specs['cable_diameter_max']['value_number']==12
    assert specs['entry_thread_designation']['value_text']=='M20x1.5'
    assert specs['ip_rating']['conditions']['requires_assembled_sealing_verification'] is True
    assert db.execute("SELECT count(*) AS n FROM product_relations WHERE relation='mates_with'").fetchone()['n']==0
