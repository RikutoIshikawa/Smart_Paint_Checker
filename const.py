#============================================================
# １.ページの設定用のパラメータ
# ・page_title：ページのタブタイトル
# ・page_icon：ページアイコン
# ・layout：画面の表示領域の幅
#============================================================
SET_PAGE_CONFIG = {
    "page_title": "イラスト着色チェックツール SmartPaintChecker",
    "page_icon": "🧊",
    "layout": "wide",
}

#============================================================
# ２.タブの設定用のパラメータ
# ・menu_title：メニューのタイトル
# ・options：メニュー項目のリスト
# ・icons：各メニューのアイコン
# ・menu_icon：タイトル横のアイコン
# ・default_index：最初に選択されるメニュー
# ・orientation：メニューの配置方向（horizontal：横）
# ・styles：メニューのスタイル設定
#============================================================
OPTION_MENU_CONFIG = {
    "menu_title": "イラスト着色チェックツール　Smart Paint Checker",
    "options": ["HOME", "機能詳細と使用例", "ツールを使用する"],
    "icons": ["bi-house", "bi-wrench", "map", "bi-rewind-fill"],
    "menu_icon": "bi-vector-pen",
    "default_index": 0,
    "orientation": "horizontal",
    "styles": {
        "container": {
            "margin": "0!important",
            "padding": "0!important",
            "background-color": "#fafafa",
        },
        "icon": {"color": "fafafa", "font-size": "25px"},
        "nav-link": {
            "font-size": "20px",
            "margin": "0px",
            "--hover-color": "#eee",
        },
        "nav-link-selected": {"background-color": "004a55"},
    },
}

#============================================================
# ３.レイアウトの調節用のパラメータ
# ・didden：非表示
# ・fixed：表示
# ・height 0%：どのくらいのスペースを使うか
#============================================================
HIDE_ST_STYLE = """
                <style>
                div[data-testid="stToolbar"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                div[data-testid="stDecoration"] {
                visibility: hidden;
                height: 0%;
                position: fixed;
                }
                #MainMenu {
                visibility: hidden;
                height: 0%;
                }
                header {
                visibility: hidden;
                height: 0%;
                }
                footer {
                visibility: hidden;
                height: 0%;
                }
				        .appview-container .main .block-container{
                            padding-top: 1rem;
                            padding-right: 3rem;
                            padding-left: 3rem;
                            padding-bottom: 1rem;
                        }  
                        .reportview-container {
                            padding-top: 0rem;
                            padding-right: 3rem;
                            padding-left: 3rem;
                            padding-bottom: 0rem;
                        }
                        header[data-testid="stHeader"] {
                            z-index: -1;
                        }
                        div[data-testid="stToolbar"] {
                        z-index: 100;
                        }
                        div[data-testid="stDecoration"] {
                        z-index: 100;
                        }
                </style>
"""