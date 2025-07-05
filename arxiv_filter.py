import requests
from bs4 import BeautifulSoup
from tkinter import filedialog
import tiktoken

import openai
import re
import time
import os

import sys
sys.stdout.reconfigure(encoding='utf-8')

# 編集する部分
safety_margin = 1000

baseline_prompt = f"""
# あなたの役割
あなたは、量子物理学の数学的基礎を専門とする理論物理学者です。あなたの任務は、渡された論文が、極めて理論的かつ数学的な探求を行う私の研究室の方針に合致するかを判定することです。

# 研究室の核心的原則
1.  **抽象性 > 応用**: 私たちは、具体的なハードウェア実装や応用例よりも、根底にある数学的な原理・構造に興味があります。
2.  **理論 > 実験**: 私たちは、物理的な実験セットアップやデータ解析ではなく、ペンと紙（あるいはそのコンピュータ版）で完結する研究を行います。

# 判定プロセス
以下の思考プロセスに従って、最終的な判断を下してください。
1.  **キーワードの確認**: 論文のタイトルと概要に「ヒルベルト空間」「作用素」「不確定性」「エンタングルメントの構造」「量子情報幾何」のような数学的な用語が多く含まれているか？
2.  **研究手法の評価**: 論文の主眼は、新しい数学的な不等式を証明したり、理論モデルを構築したりすることか？それとも、物理的なシステムを設計・実験したり、アルゴリズムの性能をシミュレーションしたりすることか？
3.  **除外項目のチェック**: 「実験」「回路」「ゲート忠実度」「デバイス」「プロトコル実装」のような、物理的実装や応用に直結する単語が含まれていないか？

# 最終的な出力
以上の思考プロセスに基づき、論文が研究室の方針に合致する場合は「〇」のみを、合致しない場合は「×」のみを出力してください。思考プロセスやその他の説明は一切出力に含めないでください。

# 評価対象の論文
"""

# 編集はしないグローバル変数/APIkey,output_path,tpm_limit

openai.api_key = 'セキュリティのため空欄に'
output_path = os.path.basename(__file__) + ".csv"	
tpm_limit = 30000

#ローカルファイルでいきます
def get_article():
	# URLからHTMLを取得
	url = 'https://arxiv.org/list/quant-ph/new'
	response = requests.get(url)
	html = response.text

	# BeautifulSoupオブジェクトを作成
	soup = BeautifulSoup(html, 'html.parser')

	# 全ての記事を含む要素を見つける
	articles = soup.find_all('dt')

	# 記事データを格納するリスト
	articles_data = []
	
	for dt in articles:
		article_data = {}
		
		# 記事のURLを抽出（PDFとAbstractの両方）
		"""
		pdf_link = dt.find('a', {'title': 'Download PDF'})
		if pdf_link:
			article_data['pdf_url'] = f"https://arxiv.org{pdf_link.get('href')}"
		"""
		abstract_link = dt.find('a', {'title': 'Abstract'})
		if abstract_link:
			article_data['abstract_url'] = f"https://arxiv.org{abstract_link.get('href')}"
		
			
		# 記事のタイトルと概要を取得
		dd = dt.find_next_sibling('dd')
		if dd:
			title_div = dd.find('div', class_='list-title')
			if title_div:
				article_data['title'] = title_div.text.replace('Title:', '').strip()
			
			abstract_p = dd.find('p', class_='mathjax')
			if abstract_p:
				article_data['abstract'] = abstract_p.text.strip()
		
		
			# 著者を取得
			authors_div = dd.find('div', class_='list-authors')
			if authors_div:
				article_data['authors'] = [a.text for a in authors_div.find_all('a')]
		

		# 記事データをリストに追加
		articles_data.append(article_data)

	return articles_data

# プロンプトと論文データを結合し、実際にどれくらいのトークン量になるか測定
def make_prompt(paper):
	title = paper.get('title')
	abstract = paper.get('abstract')
	
	content = f"""
{baseline_prompt}
Title [{title}]
Abstract: {abstract}"""

	return content

# 判断してもらうAPIコール
def check_relevance(user_data):
	response = openai.chat.completions.create(
		model="gpt-4o",
		messages=[
			{"role": "system", "content": baseline_prompt},
			{"role": "user", "content": user_data}
		],
	)
	content = response.choices[0].message.content
	print(content)

	return content

def get_token(text):
	enc = tiktoken.get_encoding("o200k_base")

	tokens = enc.encode(text)

	return len(tokens)

# 著者のリンクを作成する
# URL＋ファーストネーム＋苗字アルファベットで作成されているのでそんな感じにする
def format_author_links(authors):
	base_url = "https://arxiv.org/search/quant-ph?searchtype=author&query="
	formatted_authors = []
	
	for author in authors:

		parts = author.split()
		if len(parts) == 2:
			last_name, first_name = parts[1], parts[0][0]  # 姓と名の頭文字
			query = f"{last_name},+{first_name}"
			formatted_authors.append(f"[{author}]({base_url}{query})")
	
	return formatted_authors

# 和訳と概要を短くまとめるAPIコール関数
def abstract_to_summary_ja(abstract):

		response = openai.chat.completions.create(
		model="gpt-4o",
		messages=[
			{"role": "system", "content": "あなたは翻訳ツールです。翻訳内容以外の文章は決して出力しないでください。科学的専門用語は無理に訳さず英語表記でお願いします。この表記を変更しないでください。入力された文章を日本語で意訳し、2行にまとめなさい。"},
			{"role": "user", "content": abstract}
		],
	)
		content = response.choices[0].message.content
		return content


def main():

	papers = get_article()

	used_tokens = 0
	total_tokens = 0
	i = 1
	with open(output_path, "w", encoding="utf-8") as out:
		for paper in papers:
			# アナウンスだす
			print(f"""{i} . {paper['title']} を判定しています""", flush=True)

			user_data = f"""Title:[{paper['title']}]\nAbstract: {paper['abstract']}"""


			# トークン数の確認用処理
			# ペーパーごとにプロンプトを作成
			prompt = make_prompt(paper)

			# トークンの確認
			estimated_tokens = get_token(prompt) 

			if used_tokens + estimated_tokens > tpm_limit - safety_margin:
				print("トークン数が制限に達しそうです", flush=True)
				print("1分の処理待ちをします", flush=True)
				time.sleep(60)
				used_tokens = 0

			#総合トークン数は個人的興味
			used_tokens += estimated_tokens
			total_tokens += estimated_tokens
			print(f"""蓄積トークン数: {used_tokens}""", flush=True)

			# 本処理
			match = re.search(r'[〇]', check_relevance(user_data))
			if match:
				paper['is_relevant'] = True
				out.write(f"""{i}\tmatch\n""")
			else:
				paper['is_relevant'] = False
				out.write(f"""{i}\tnot\n""")

			i += 1

		relevant_papers = [p for p in papers if p['is_relevant']]

	for paper in relevant_papers:

		# 和訳プロンプトを通して、マークダウンで出力する
		md_text = f"""
*[{paper['title']}]({paper['abstract_url']})*
著者: {format_author_links(paper['authors']):}
概要: {abstract_to_summary_ja(paper['abstract'])}
			
			"""
		print(md_text)

	print(f"""累計トークン数: {total_tokens}""")
	input("終了するにはEnterキーを押してください")

if __name__ == "__main__":
	main()