import json
from istina.model.entities.article import Article

def test_json_serializable():
    article = Article.create(title="T", url="http://x", source="Y")
    d = article.to_dict()
    j = json.dumps(d)
    d2 = json.loads(j)
    article2 = Article.from_dict(d2)
    assert article == article2  # This will be True if the id matches

