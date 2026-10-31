from wain.candidates import parse_line,extract
from test_database import db

def test_multiple_products_in_one_table_row():
    found=list(parse_line('CESM-0.37 101 019 110 0301 CESF-0.37 101 019 120 0301'))
    assert [(r['model_candidate'],r['order_number_candidate']) for r in found]==[
        ('CESM-0.37','1010191100301'),('CESF-0.37','1010191200301')]

def test_dimensions_and_ratings_are_not_order_numbers():
    assert list(parse_line('250V 16A 10+PE 49.5 56 7.5 2.5mm2'))==[]

def test_staging_is_idempotent_and_not_promoted(db):
    db.execute("UPDATE pages SET ocr_text='HA-010-MC 121 010 010 0001',ocr_status='done' WHERE global_page=76")
    assert extract(db)['new_candidates']==1
    assert extract(db)['new_candidates']==0
    assert db.execute('SELECT count(*) AS n FROM products').fetchone()['n']==48
    assert db.execute('SELECT review_status FROM product_candidates').fetchone()['review_status']=='pending'
