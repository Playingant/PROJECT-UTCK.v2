import sqlite3
import requests
import threading
import time
from datetime import datetime
from collections import Counter
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify

# --- [설정 및 타겟 데이터] ---
DB_NAME = "artist_monitor.db"
SCAN_INTERVAL = 3600 # 1시간 간격

# 타겟 사이트 설정
TARGETS = {
    "dc": {
        "name": "버츄얼 스나이퍼",
        "url": "https://gall.dcinside.com/mini/board/lists?id=vtubersnipe",
        "selector": ".ub-content.us-post .gall_tit a",
        "keywords": ["굴깨", "굴세돌", "굴계돌", "이파리", "아이네", "징버거", "주르르", "릴파", "비챤", "고세구", "포차", "굴"],
        "table": "logs_dc"
    },
    "ruli": {
        "name": "루리웹 (이세돌)",
        "url": "https://bbs.ruliweb.com/hobby/board/300143",
        "selector": ".subject .relative",
        "keywords": ["이세계아이돌", "이세돌", "아이네", "징버거", "릴파", "주르르", "고세구", "비챤"],
        "table": "logs_ruli"
    }
}

app = Flask(__name__)

# --- [데이터베이스 및 모니터링 엔진 로직] ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 각 타겟별 테이블 생성
    for config in TARGETS.values():
        c.execute(f'''CREATE TABLE IF NOT EXISTS {config['table']} 
                     (timestamp TEXT, count INTEGER, keywords TEXT)''')
    conn.commit()
    conn.close()

def save_data(table, timestamp, count, keywords_str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"INSERT INTO {table} VALUES (?, ?, ?)", (timestamp, count, keywords_str))
    conn.commit()
    conn.close()

def monitoring_loop():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    while True:
        now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for key, config in TARGETS.items():
            try:
                res = requests.get(config["url"], headers=headers, timeout=10)
                soup = BeautifulSoup(res.text, 'html.parser')
                posts = soup.select(config["selector"])
                found = []
                for p in posts:
                    title = p.text.strip()
                    for k in config["keywords"]:
                        if k in title:
                            found.append(k)
                            break
                save_data(config["table"], now_time, len(found), ",".join(found))
            except Exception as e:
                print(f"[{key}] 데이터 수집 오류: {e}")
        time.sleep(SCAN_INTERVAL)

# --- [Web API] ---
@app.route('/api/stats/<site>')
def get_stats(site):
    config = TARGETS.get(site)
    if not config: return jsonify({"error": "invalid site"}), 400
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 최근 24시간 데이터 가져오기 (시간 순)
    c.execute(f"SELECT timestamp, count, keywords FROM {config['table']} ORDER BY timestamp DESC LIMIT 24")
    rows = c.fetchall()
    conn.close()
    
    # 시간 순 정렬
    rows = rows[::-1]
    labels = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    
    # 최근 기록 5개 (내림차순)
    recent_logs = []
    for r in rows[-5:]:
        recent_logs.append({
            "time": r[0],
            "count": r[1],
            "keywords": r[2] if r[2] else "탐지 내용 없음"
        })

    return jsonify({
        "labels": labels,
        "counts": counts,
        "daily_total": sum(counts),
        "recent_logs": recent_logs
    })

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# --- [웹 UI 코드 (HTML/CSS/JS)] ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARTIST : UTCK</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Noto+Sans+KR:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Noto Sans KR', sans-serif; background-color: #FAFAFA; color: #111; }
        .tab-btn.active { background-color: #111; color: white; border-color: #111; }
        .chart-container { background: #FFFFFF; border: 1px solid #EEEEEE; box-shadow: 0 10px 30px rgba(0,0,0,0.03); }
        .log-item { border-bottom: 1px solid #F0F0F0; padding: 15px 0; }
        .log-item:last-child { border-bottom: none; }
        .accent-point { color: #2E7D32; } /* 은은한 초록 색감 추가 */
    </style>
</head>
<body class="p-4 md:p-8">

    <div class="max-w-6xl mx-auto">
        <nav class="flex justify-between items-center pb-8 border-b-2 border-gray-100 mb-10">
            <h1 class="text-3xl font-black font-[Montserrat] accent-point">ARTIST.UTCK</h1>
            <div class="flex gap-2">
                <button onclick="changeSite('dc')" id="btn-dc" class="tab-btn active px-6 py-2 rounded-full border border-gray-200 text-sm font-bold">버츄얼 스나이퍼</button>
                <button onclick="changeSite('ruli')" id="btn-ruli" class="tab-btn px-6 py-2 rounded-full border border-gray-200 text-sm font-bold">루리웹 (이세돌)</button>
            </div>
        </nav>

        <main class="space-y-8">
            <header>
                <p id="main-label" class="text-gray-400 font-medium">실시간 커뮤니티 데이터 분석 현황입니다.</p>
            </header>

            <div class="chart-container rounded-3xl p-8 flex flex-col justify-center items-center h-48">
                <p class="text-gray-400 text-sm uppercase tracking-widest font-bold mb-4">현재까지 총 탐지 수</p>
                <h2 id="total-detect" class="text-6xl font-black">0건</h2>
            </div>

            <div class="chart-container rounded-3xl p-8">
                <h3 class="text-xl font-bold mb-6">최근 24시간 탐지 트렌드</h3>
                <div class="h-80">
                    <canvas id="trendChart"></canvas>
                </div>
            </div>

            <div class="chart-container rounded-3xl p-8">
                <h3 class="text-xl font-bold mb-6">최근 모니터링 기록</h3>
                <div id="log-list">
                    </div>
            </div>
        </main>
    </div>

    <script>
        let currentSite = 'dc';
        let mainChart = null;

        async function updateData() {
            try {
                const res = await fetch(`/api/stats/${currentSite}`);
                const data = await res.json();

                // UI 업데이트
                document.getElementById('total-detect').innerText = data.daily_total + '건';
                document.getElementById('main-label').innerText = `${currentSite === 'dc' ? '버츄얼 스나이퍼' : '루리웹'} 데이터 분석 현황입니다.`;

                // 차트 업데이트
                const ctx = document.getElementById('trendChart').getContext('2d');
                if (mainChart) mainChart.destroy();
                mainChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.labels.map(l => l.split(' ')[1].substring(0,5)),
                        datasets: [{
                            data: data.counts,
                            borderColor: '#111',
                            borderWidth: 3,
                            pointRadius: 0,
                            tension: 0.4,
                            fill: false,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, grid: { color: '#F0F0F0' } },
                            x: { grid: { display: false } }
                        }
                    }
                });

                // 로그 리스트 업데이트
                const list = document.getElementById('log-list');
                list.innerHTML = data.recent_logs.map(log => `
                    <div class="log-item flex justify-between">
                        <span class="text-gray-400 text-sm">${log.time.split(' ')[1]}</span>
                        <span class="font-bold flex-1 text-center">${log.count}개의 금칙어 탐지</span>
                        <span class="text-gray-400 text-xs truncate max-w-xs">${log.keywords}</span>
                    </div>
                `).join('');

            } catch (error) { console.error("데이터 로드 실패:", error); }
        }

        // 전환 함수
        function changeSite(site) {
            currentSite = site;
            // 버튼 스타일 전환
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`btn-${site}`).classList.add('active');
            updateData();
        }

        window.onload = updateData;
        setInterval(updateData, 60000); // 1분마다 업데이트
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    init_db()
    # 모니터링 스레드 실행
    threading.Thread(target=monitoring_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)