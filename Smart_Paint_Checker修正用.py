#=================================================================
# インポート
#=================================================================
import streamlit as st
import psd_tools
import const
from streamlit_option_menu import option_menu
from PIL import Image, ImageDraw
import numpy as np
import cv2
from io import BytesIO
from scipy.ndimage import label
from collections import Counter
import zipfile
import hashlib

#=================================================================
# 各機能関数
#=================================================================
def SelectionColor_Display_System(psd, colors, thresholds, background):
#仮引数：psdファイル、表示するカラーリスト、各カラーの許容範囲リスト、背景カラー
    #背景カラーをRGB値へ変換
    if isinstance(background, str) and background.startswith("#"):
        background = background.lstrip('#')
        r = int(background[0:2], 16)
        g = int(background[2:4], 16)
        b = int(background[4:6], 16)
        background = (r, g, b)
    #出力画像の生成
    result_img = Image.new("RGBA", psd.composite().size, (background[0], background[1], background[2], 255))
    #表示するカラー数だけ繰り返し
    for (color, threshold) in zip(colors, thresholds):
        #表示するカラーをRGB値へ変換
        if isinstance(color, str) and color.startswith("#"):
            color = color.lstrip('#')
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
        #レイヤーを解析
        for layer in psd.descendants():
            if not layer.is_group():
                layer_img = layer.topil()    
                if layer_img is None:
                    continue
                layer_np = np.array(layer_img)
                #レイヤ画像が透過度を持つかを判定
                if layer_np.shape[2] == 4:
                    alpha = layer_np[:, :, 3]
                    #透明度が０より大きいピクセルを取得
                    valid_pixels = alpha > 0
                else:
                    #透過度を持たない場合は全てのピクセルを取得
                    valid_pixels = np.ones(layer_np.shape[:2], dtype=bool)
                #指定カラーとの差を計算し、閾値内の色を一致とみなす
                mask = (np.abs(layer_np[:, :, 0] - r) <= threshold[0]) & \
                       (np.abs(layer_np[:, :, 1] - g) <= threshold[1]) & \
                       (np.abs(layer_np[:, :, 2] - b) <= threshold[2]) & valid_pixels
                alpha_channel = np.where(mask, 255, 0).astype(np.uint8)
                result_layer = np.dstack((layer_np[:, :, :3], alpha_channel))
                layer_img = Image.fromarray(result_layer, "RGBA") 
                result_img.paste(layer_img, (layer.left, layer.top), layer_img)
    return result_img 

def SelectionLayers_Contour_System(psd, layers, threshold, color, contour_size, layer_display_switching, background_display_switching, background):
#仮引数：表示するレイヤー画像、二値化の閾値、輪郭線のカラー、輪郭線の幅、レイヤー画像の表示切替、背景の表示切替、背景カラー
    #輪郭線のカラーと背景カラーをRGB値へ変換
    if isinstance(color, str) and color.startswith("#"):
        color = color.lstrip('#')
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        color = (b, g, r)
    if isinstance(background, str) and background.startswith("#"):
        background = background.lstrip('#')
        r = int(background[0:2], 16)
        g = int(background[2:4], 16)
        b = int(background[4:6], 16)
        background = (r, g, b)
    #出力画像の生成
    background = Image.new("RGBA", psd.composite().size, (background[0], background[1], background[2], 255))
    #レイヤー画像をNumpy配列に変換
    layers_np = np.array(layers, dtype=np.uint8)
    #RGBAからBGRに変換
    layers_bgr = cv2.cvtColor(layers_np, cv2.COLOR_RGBA2BGR)
    #グレースケールに変換
    layers_gray = cv2.cvtColor(layers_bgr, cv2.COLOR_BGR2GRAY)
    #二値化
    ret, binary = cv2.threshold(layers_gray, threshold, 255, cv2.THRESH_BINARY)
    #輪郭を検出
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    #全て白または黒のカラー画像を作成
    if color == (255, 255, 255):
        #背景は黒（輪郭は白）
        img_blank = np.zeros_like(layers_bgr, dtype=np.uint8)
    else:
        #背景は白（輪郭は白以外）
        img_blank = np.ones_like(layers_bgr, dtype=np.uint8) * 255
    #輪郭を描画
    contour_img = cv2.drawContours(img_blank, contours, -1, color, contour_size)
    #OpenCV形式からPillow形式に変換
    result_img = Image.fromarray(cv2.cvtColor(contour_img, cv2.COLOR_BGRA2RGBA))
    #輪郭以外を透過させる（R, G, B がすべて 255）の場合、アルファ値を 0 に設定
    datas = result_img.getdata()
    new_data = []
    if color == (255, 255, 255):
        for item in datas:
            #輪郭以外（黒）を透過させる
            if item[0] == 0 and item[1] == 0 and item[2] == 0:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        result_img.putdata(new_data)
    else:
        for item in datas:
            #輪郭以外（白）を透過させる
            if item[0] == 255 and item[1] == 255 and item[2] == 255:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        result_img.putdata(new_data)
    #輪郭とレイヤー画像を合成
    if layer_display_switching == "表示":
        result_img.paste(layers, (psd.left, psd.top), layers)
    if background_display_switching == "表示":
        background.paste(result_img, (psd.left, psd.top), result_img)
        result_img = background
    return result_img

def MissingPaint_Detection_System1(psd, selected_color, split_scale, line_scale):
#仮引数：psdファイル、背景カラー、出力画像の分割数、矩形の線の太さ
    low_colors  = {"Red":(0, 0, 200), "Green":(0, 200, 0), "Blue":(250, 0, 0)}
    high_colors = {"Red":(0, 0, 255), "Green":(0, 255, 0), "Blue":(255, 0, 0)}
    bg_colors   = {"Red":(255, 0, 0, 255), "Green":(0, 255, 0, 255), "Blue":(0, 0, 255, 255)}
    line_colors = {"Red":(0, 255, 0), "Green":(0, 0, 255), "Blue":(0, 255, 255)}
    
    bg_color = bg_colors[selected_color]
    Low = np.array(low_colors[selected_color])
    High = np.array(high_colors[selected_color])
    #全体を黒くする処理
    psd_composite = psd.composite()
    dummy = psd_composite.copy()
    dst_color = (0, 0, 0)
    mask_pil = psd_composite.convert('L')
    mask_pil = Image.eval(mask_pil, lambda x: 255 - x)
    psd_composite.paste(Image.new("RGB", psd_composite.size, dst_color), mask= mask_pil)
    #OpenCV形式に変換
    psd_np = np.array(psd_composite)
    psd_cv = cv2.cvtColor(psd_np, cv2.COLOR_RGB2BGR)
    #画像をグレースケール化
    psd_gray = cv2.cvtColor(psd_cv, cv2.COLOR_RGB2GRAY)
    #画像を2値化してマスク生成
    psd_mask = cv2.threshold(psd_gray, 254, 255, cv2.THRESH_BINARY_INV)[1]
    kernel = np.ones((3,3),np.uint8)
    image_mask_1 = cv2.threshold(psd_gray, 254, 255, cv2.THRESH_BINARY_INV)[1]
    psd_mask = cv2.dilate(image_mask_1 ,kernel,iterations = 3)
    #PIL形式に戻す
    img = cv2.cvtColor(psd_mask, cv2.COLOR_BGR2RGB)
    mask = Image.fromarray(img)
    #作成したマスクを2値化用フォーマットにする
    mask = mask.convert('L')
    #マスクで切り抜いて透過
    psd_composite.putalpha(mask)
    #背景画像の作成
    im0 = Image.new('RGBA', psd.size, bg_color)
    #背景用画像と検品対象を合成
    result_img = Image.composite(dummy, im0, mask)
    pil2_numpy = np.array(result_img)
    image2_cv = cv2.cvtColor(pil2_numpy, cv2.COLOR_RGB2BGR)
    #指定色に対してマスクの作成
    mask = cv2.inRange(image2_cv, Low, High)
    #輪郭取得
    contours, hierarchy = cv2.findContours(
    mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    #塗り漏れ検知部分に矩形を描画 + 検知部分を拡大
    result_img_list = [] #出力画像リスト
    display_count = 1  #検出数
    display_limit = 100 #表示画像数の限度
    for i, cnt in enumerate(contours):
        #条件: 表示した検知部分がdisplay_limit以下
        if display_count < display_limit:
            #取得した輪郭の面積が特定の範囲内
            if 10 < cv2.contourArea(cnt) < 10000:
                display_count+=1
                #所得した輪郭の座標を特定
                x, y, width, hight = cv2.boundingRect(cnt)

                linecolor = line_colors[selected_color]
                #矩形描画
                cv2.rectangle(image2_cv, (x, y), (x+width, y+hight), linecolor, line_scale)
        else:
            break
    splits = split_scale
    
    #n : 分割用の値
    n = np.floor(np.sqrt(splits))
    n = int(n)
    imHight = int(image2_cv.shape[0])//n 
    imWidth = int(image2_cv.shape[1])//n
    #print(f'imWidth : {imWidth}\nimHight : {imHight}')
    
    #初期値の設定
    start  = 0
    stop = imHight
    high_list = []
    images = []
    
    #横方向に分割
    for i in range (splits):
        if(stop <= image2_cv.shape[0]):
            cliped = image2_cv[start:stop, :image2_cv.shape[1]]
            high_list.append(cliped)
            start += imHight
            stop += imHight
            
    #横方向に分割した物をひとつづつ取り出して縦方向に分割する
    for image in high_list:
        start = 0
        stop = imWidth
        for j in range(n):
            if(stop <= image2_cv.shape[1]):
                cliped = image[:imHight, start:stop]
                images.append(cliped)
                start += imWidth
                stop += imWidth
                #print(f'start :{start}\nstop :{stop}')

    for image in images:
        resize = cv2.resize(image, None, fx=1.0, fy=1.0)
        conve = cv2.cvtColor(resize, cv2.COLOR_BGR2RGB)
        result = Image.fromarray(conve)
        result_img_list.append(result)

    return result_img_list

def LineDrawingMistake_Detection_System1(psd, line, threshold):
#仮引数：psdファイル、線画画像、検知箇所の統合判定距離
    #線画の色を緑色に変更
    line_np = np.array(line)
    line_color = [0, 255, 0, 255]
    #線画部分（アルファ値が0でない部分）を緑色に変更
    mask = line_np[:, :, 3] > 0
    line_np[mask] = line_color
    #RGBAからBGRに変換
    line_bgr = cv2.cvtColor(line_np, cv2.COLOR_RGBA2BGR)
    #グレースケールに変換
    line_gray = cv2.cvtColor(line_bgr, cv2.COLOR_BGR2GRAY)
    #二値化（150を閾値に設定）
    ret, binary = cv2.threshold(line_gray, threshold, 255, cv2.THRESH_BINARY)
    #線画の輪郭の検出
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
    )
    #輪郭の描画
    img_blank = np.ones_like(line_bgr, dtype=np.uint8) * 255
    contours_img = cv2.drawContours(img_blank , contours, -1, color=(0, 0, 255), thickness=5)
    #検知箇所の座標
    circle_centers = []
    #近い線画を合成後の検知箇所の座標
    filtered_centers = []
    #検出数
    count = 0
    #検知箇所の座標計算
    for cnt in contours:
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        center = (int(x), int(y))
        area = cv2.contourArea(cnt)
        if (10 < area < 100 ):
            circle_centers.append(center)
    #重複検出と円描画
    for i, center1 in enumerate(circle_centers):
        check = False
        for j, center2 in enumerate(filtered_centers):
            distance = np.linalg.norm(np.array(center1) - np.array(center2))
            if distance < threshold:
                check = True
                break    
        if not check:
            filtered_centers.append(center1)
    for center in filtered_centers:
        cv2.circle(contours_img, center, 50, (255, 0, 0), 10)
        count+=1
    result_img = Image.fromarray(contours_img.astype(np.uint8))
    return result_img

def MissingPaint_Detection_System2(psd, color, tolerance, circle_radius, max_region_size):
#仮引数：psdファイル、検知箇所カラー、色の許容誤差、円の半径、塗り漏れと判定する領域のサイズ
    if isinstance(color, str) and color.startswith("#"):
        color = color.lstrip('#')
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        color = (r, g, b)
    #背景画像を作成
    psd_width, psd_height = psd.width, psd.height
    background_img = Image.new("RGB", (psd_width, psd_height), color)
    background_img_rgba = background_img.convert("RGBA")
    #既存のPSDファイルのレイヤーを合成
    existing_layers = psd.topil()
    #背景と合成して最終画像を作成
    result_img = Image.alpha_composite(background_img_rgba, existing_layers.convert("RGBA"))
    #蛍光色の領域を検出
    img_array = np.array(result_img.convert("RGB"))
    r, g, b = color
    mask = np.all(np.abs(img_array - np.array([r, g, b])) <= tolerance, axis=-1)
    #連結した領域を結合し、ラベリング
    labeled_array, num_features = label(mask)
    #領域サイズの確認と円の描画
    draw = ImageDraw.Draw(result_img)
    for region_num in range(1, num_features + 1):
        region_mask = (labeled_array == region_num)
        region_size = np.sum(region_mask)
        if region_size <= max_region_size:
            region_indices = np.argwhere(region_mask)
            y_min, x_min = region_indices.min(axis=0)
            y_max, x_max = region_indices.max(axis=0)
            center_x = (x_min + x_max) // 2
            center_y = (y_min + y_max) // 2
            draw.ellipse(
                (center_x - circle_radius, center_y - circle_radius,
                 center_x + circle_radius, center_y + circle_radius),
                outline=(0, 255, 0), width=2)
    return result_img

def LineDrawingMistake_Detection_System2(psd, line):
#仮引数：psdファイル、線画画像
    #グレースケールに変換
    line_gray = line.convert("L") 
    #ノイズ除去
    line_gray = cv2.GaussianBlur(np.array(line_gray), (5, 5), 0)
    #二値化
    binary = cv2.adaptiveThreshold(line_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    #連結領域ごとにラベルを付ける
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    #ランダムな色を生成
    output = np.zeros((*binary.shape, 3), dtype=np.uint8)
    colors = []
    for label in range(1, num_labels):#ラベル0は背景
        area = stats[label, cv2.CC_STAT_AREA]
        #最小領域サイズを設定し、ノイズ除去
        if area > 50:
            mask = (labels == label)
            color = np.random.randint(0, 255, size=3)
            output[mask] = color
            colors.append(tuple(color))
    #線画にエラーがある場合
    if colors:
        #最も多く使われている色を計算
        most_common_color = Counter(colors).most_common(1)[0][0]
        #最も多く使われている色をピンクに着色
        light_pink = (255, 182, 193)
        output[np.all(output == most_common_color, axis=-1)] = light_pink
        #半径を記録するリスト
        radii = []
        #各線画ラベルに円を描画
        for label in range(1, num_labels):
            mask = (labels == label)
            points = np.argwhere(mask)
            if points.size > 0:
                #領域の重心を計算
                center = points.mean(axis=0).astype(int)
                #半径を計算
                radius = max(np.linalg.norm(points - center, axis=1).max(), 5)
                #半径と重心をリストに追加
                radii.append((radius, center))
        #半径で降順ソート
        radii.sort(reverse=True, key=lambda x: x[0])
        #半径が最大の円を除外
        max_radius = radii[0][0]
        radii = [r for r in radii if r[0] < max_radius]
        #円を描画
        for radius, center in radii:
            #円を拡大
            cv2.circle(output, tuple(center[::-1]), int(radius * 1.2), (0, 255, 0), 2)
        result_img = Image.fromarray(output)
        return result_img     
    else:
        return 0

#=================================================================
# ページ、レイアウト設定
# ・SET_PAGE_CONFIG：ページの設定
# ・HIDE_ST_STYLE：レイアウトの調節
# ・OPTION_MENU_CONFIG：タブの設定
# ・st.markdown：markdown設定
#=================================================================
st.set_page_config(**const.SET_PAGE_CONFIG)
st.markdown(const.HIDE_ST_STYLE, unsafe_allow_html=True)
selected = option_menu(**const.OPTION_MENU_CONFIG)
st.markdown('''
<style>.my-text {
    color: white;
    font-size: 24px;
    background-color: #008080;
    padding: 10px;
    border-radius: 10px;
}</style>

<style>.box {
    background:#c4d9ff;
    border-left:#4e7bcc 5px solid;
    padding:2px;
    width: 300px;
    font-size: 20px;
    text-align: center; 
}</style>

<style>.box2{
    background:#c4d9ff;
    border-left:#4e7bcc 5px solid;
    padding:2px;
    width: 400px;
    font-size: 20px;
    text-align: center; 
}</style>''', unsafe_allow_html=True)
    
#=================================================================
# HOME画面
#=================================================================
if selected == 'HOME':
    st.markdown('''
    <p class='my-text'>デジタルイラスト制作における課題と本研究の目的</p>
    
    ゲーム会社など、デジタルイラストを大量に扱う企業では、外部のイラスト制作会社に業務を委託することがある。  
    そして、委託を受けた制作会社は完成したイラストを納品する前に、品質を保証するため「塗り漏れ」「はみ出し」「消し忘れ」などのミスがないかを細部までチェックする必要がある。 
    しかし、これらのチェック作業は従来、手作業で行われており、手間がかかるという課題が指摘されている。  
    そこで本研究では、画像処理技術を用いて「塗り漏れ」「はみ出し」「消し忘れ」ミスを自動的に検知、または発見を支援する方式を提案する。  
    さらに、これらの方式に基づいてイラストの着色チェックツール「Smart Paint Checker」を開発することで、ミスチェック作業の効率化とクリエイターの負担軽減を図ることを目的とする。
    ''', unsafe_allow_html=True)
    st.image('./Images/ミス一覧.png', width=700) 
    
    st.markdown('''
    <p class='my-text'>開発体制</p>
    
    ##### 組織名
    東京電機大学 システムデザイン工学部 情報システム工学科 マルチメディアコンピューティング研究室
    
    ##### メンバー
    ・石川 陸斗：全体システム、指定色表示システム、指定レイヤ輪郭表示システム 開発担当  
    ・染谷 学玖：塗り漏れ検知システム２、消し忘れ検知システム２ 開発担当  
    ・中野 爽一朗：塗り漏れ検知システム１、消し忘れ検知システム１ 開発担当  
    ''', unsafe_allow_html=True)
    link = '[研究室へのご連絡はこちらから](https://mclab.jp/?page_id=368)'
    st.markdown(link, unsafe_allow_html=True)
    
    st.markdown('''
    <p class='my-text'>使用したイラスト素材</p>
    
    ##### ユニティちゃん
    <div><img src="https://unity-chan.com/images/imageLicenseLogo.png" alt="ユニティちゃんライセンス"><p>
    
    『<a href="https://unity-chan.com/contents/license_jp/" target="_blank">ユニティちゃんライセンス</a>』  
    『<a href="https://unity-chan.com/contents/guideline/" target="_blank">キャラクター利用のガイドライン</a>』
    ''', unsafe_allow_html=True)
    
#=================================================================
# 機能詳細と使用例画面
#=================================================================
if selected == '機能詳細と使用例':
    st.markdown('''
    <p class='my-text'>機能１：指定カラー表示システム</p>
    <p class='box'>機能内容</p>
    
    イラストファイルとカラーを指定することで、イラスト内でそのカラーが使用されている箇所のみを表示する機能である。  
    また、塗りの濃さが異なる場合を考慮し、RGB各値に許容範囲（±）を指定することや複数のカラーを同時に指定することも可能である。  
    ''', unsafe_allow_html=True)
    st.image('./Images/指定色表示_機能内容.png', width=700) 
    st.markdown('''<p class='box'>使用事例</p>''', unsafe_allow_html=True)
    st.image('./Images/指定色表示_使用例.png', width=700) 
        
    st.markdown('''
    <p class='my-text'>機能２：指定レイヤー輪郭表示システム</p>
    <p class='box'>機能内容</p>
    
    イラストファイルとレイヤーを指定することで、そのレイヤー画像と輪郭を表示する機能である。  
    また、レイヤー画像を非表示にして輪郭のみを表示することや複数のレイヤーを同時に指定することも可能である。
    ''', unsafe_allow_html=True)
    st.image('./Images/指定レイヤ輪郭表示_機能内容.png', width=700) 
    st.markdown('''<p class='box'>使用事例</p>''', unsafe_allow_html=True)
    st.image('./Images/指定レイヤ輪郭表示_使用例１.png', width=700) 
    st.image('./Images/指定レイヤ輪郭表示_使用例２.png', width=700) 
    
    
    st.markdown('''
    <p class='my-text'>機能３：塗り漏れ検知システム１</p>
    <p class='box'>機能内容</p>''', unsafe_allow_html=True)
    st.markdown('''<p class='box'>特徴</p>''', unsafe_allow_html=True)
    
    st.markdown('''
    <p class='my-text'>機能４：塗り漏れ検知システム２</p>
    <p class='box'>機能内容</p>''', unsafe_allow_html=True)
    st.markdown('''<p class='box'>特徴</p>''', unsafe_allow_html=True)
    
    st.markdown('''
    <p class='my-text'>機能５：消し忘れ検知システム１</p>
    <p class='box'>機能内容</p>''', unsafe_allow_html=True)
    st.markdown('''<p class='box'>特徴</p>''', unsafe_allow_html=True)
    
    st.markdown('''
    <p class='my-text'>機能６：消し忘れ検知システム２</p>
    <p class='box'>機能内容</p>''', unsafe_allow_html=True)
    st.markdown('''<p class='box'>特徴</p>''', unsafe_allow_html=True)
    
#=================================================================
# ツールを使用する画面
#=================================================================
if selected == 'ツールを使用する':
    #========================================
    # 「機能の選択」
    #========================================
    st.markdown('''
    <p class='my-text'>機能の選択</p>
    
    #### 以下から使用したい機能を選択してください。（:red[複数同時実行可能]）''', unsafe_allow_html=True)
    
    functions = []
    if st.checkbox('指定カラー表示システム'):
        functions.append('SelectionColor_Display_System')
    st.write('<span style="color:red;background:pink">：イラスト内で指定したカラーが使用されている箇所を表示する</span>'
    ,unsafe_allow_html=True)
    if st.checkbox('指定レイヤー輪郭表示システム'):
        functions.append('SelectionLayers_Contour_System')
    st.write('<span style="color:red;background:pink">：指定したレイヤー画像の輪郭を抽出する</span>'
    ,unsafe_allow_html=True)
    if st.checkbox('塗り漏れ検知システム１'):
        functions.append('MissingPaint_Detection_System1')
    st.write('<span style="color:red;background:pink">：イラスト内の「塗り漏れ」を検知する</span>'
    ,unsafe_allow_html=True)
    if st.checkbox('塗り漏れ検知システム２'):
        functions.append('MissingPaint_Detection_System2')
    st.write('<span style="color:red;background:pink">：イラスト内の「塗り漏れ」を検知する</span>'
    ,unsafe_allow_html=True)
    if st.checkbox('消し忘れ検知システム１'):
        functions.append('LineDrawingMistake_Detection_System1')
    st.write('<span style="color:red;background:pink">：線画の「消し忘れ」を検知する</span>'
    ,unsafe_allow_html=True)
    if st.checkbox('消し忘れ検知システム２'):
        functions.append('LineDrawingMistake_Detection_System2')
    st.write('<span style="color:red;background:pink">：線画の「消し忘れ」を検知する</span>'
    ,unsafe_allow_html=True)
    
    #========================================
    # 「ファイルの選択」
    #========================================
    st.markdown('''<p class='my-text'>ファイルの選択</p>''', unsafe_allow_html=True)
    #セッション変数の初期化（エラー判定・レイヤー一覧用）
    if "last_file_hash1" not in st.session_state:
        st.session_state.last_file_hash1 = None
    if "last_file_hash2" not in st.session_state:
        st.session_state.last_file_hash2 = None
    if "error_flag" not in st.session_state:
        st.session_state.error_flag = None
    if "name_list" not in st.session_state:
        st.session_state.variable_value = []
    if "img_list" not in st.session_state:
        st.session_state.variable_value = []
    if "layer_number" not in st.session_state:
        st.session_state.variable_value = 0
    #ファイルのアップロード
    uploaded_file = st.file_uploader('#### 使用するPSDファイルを選択してください。', type='psd')
    if uploaded_file is not None:
        #ファイルのハッシュ値を計算
        uploaded_file.seek(0)
        file_hash = hashlib.sha256(uploaded_file.read()).hexdigest()
        uploaded_file.seek(0)
        current_file_hash = file_hash
        psd = psd_tools.PSDImage.open(uploaded_file)
        psd_composite = psd.composite()
        
        #========================================
        # 「エラー判定」
        #========================================
        #入力ファイルが変更されたかを判定
        if st.session_state.last_file_hash1 != current_file_hash:
            #エラーイラストの判定
            psd_pixels = psd_composite.getdata()
            total_pixels = len(psd_pixels)
            empty_pixels = sum(1 for psd_pixel in psd_pixels if len(psd_pixel) > 3 and psd_pixel[3] == 0)
            #セッション変数を更新（エラー判定用）
            if empty_pixels == total_pixels:
                st.session_state.error_flag = 'エラー'
            else:
                st.session_state.error_flag = '正常'
            st.session_state.last_file_hash1 = current_file_hash
        #判定結果の出力
        if st.session_state.error_flag == 'エラー':
            st.error('透明な画像が入力されました。画像を変更してください。')
        else:
            st.success('アップロードが完了しました。')
            
            #========================================
            # 「レイヤ一覧の表示」
            #========================================
            st.markdown('''
            <p class='my-text'>線画レイヤーの選択</p>
            
            #### 一覧を基に線画レイヤーを選択してください。''', unsafe_allow_html=True)
            name_list = []
            img_list = []
            layer_number = 0
            #入力ファイルが変更されたかを判定
            if st.session_state.last_file_hash2 != current_file_hash:
                for layer in psd.descendants():
                    if not layer.is_group():
                        layer.visible = True
                        if not layer.clipping_layer:
                            base_img = layer.composite()
                            if base_img != None:
                                name_list.append(layer.name)
                                resized_img = base_img.resize((150, 150), Image.Resampling.LANCZOS)
                                img_list.append(resized_img)
                                layer_number += 1
                #セッション変数を更新（レイヤー一覧表示用）
                st.session_state.name_list = name_list
                st.session_state.img_list = img_list
                st.session_state.layer_number = layer_number
                st.session_state.last_file_hash2 = current_file_hash
            else:
                #ステートを利用（レイヤー一覧表示用）
                name_list = st.session_state.name_list
                img_list = st.session_state.img_list
                layer_number = st.session_state.layer_number
            #レイヤー一覧の表示
            st.text(f'レイヤー数:{layer_number}')
            cols = st.columns(10)
            for i, img in enumerate(img_list):
                col = cols[i % 10]
                col.image(img, caption=name_list[i], use_column_width=True)
            
            #========================================
            # 「線画レイヤーの選択」
            #========================================
            #セッション変数の初期化（線画レイヤーの選択用）
            if "selected_layers" not in st.session_state:
                st.session_state.selected_layers = []
            if "line_img" not in st.session_state:
                st.session_state.line_img = None
            #レイヤーの選択
            selected_layers = st.multiselect(
                '###### ～複数選択可能（線画が分かれている場合等）～', 
                name_list, 
            )
            line_img = Image.new("RGBA", psd_composite.size, (255, 255, 255, 0))
            if selected_layers:
                #選択レイヤーが変更されていないかを確認
                if selected_layers == st.session_state.selected_layers:
                    line_img = st.session_state.line_img
                else:
                    #========================================
                    # 「線画の合成」
                    #========================================
                    for layer in psd.descendants():
                        for item in selected_layers:
                            if layer.name == item and not layer.is_group():
                                layer_img = layer.composite()
                                line_img.paste(layer_img, (layer.left, layer.top), layer_img)
                    #セッション変数を更新（線画レイヤーの選択用）
                    st.session_state.selected_layers = selected_layers
                    st.session_state.line_img = line_img
                line_resized = line_img.resize((256, 256), Image.LANCZOS)
                st.markdown('''<p class='box'>選択された線画レイヤー画像</p>''', unsafe_allow_html=True)
                st.image(line_resized)
            else:
                st.error('線画レイヤーが選択されていません。')
            
            #========================================
            # 「パラメータの調整」と「出力」
            #========================================
            if functions:
                #出力結果ダウンロード用のzipファイルを作成
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for function in functions:
                        #指定カラー表示システム
                        if function == 'SelectionColor_Display_System':
                            st.markdown('''
                            <p class='my-text'>指定カラー表示システム</p>
                            <p class='box'>表示するカラーを選択</p>''', unsafe_allow_html=True)
                            if 'color_count' not in st.session_state:
                                st.session_state.color_count = 1
                            if st.button('カラーを増やす'):
                                st.session_state.color_count += 1
                            if st.button('カラーを減らす') and st.session_state.color_count > 1:
                                st.session_state.color_count -= 1
                            colors = []
                            thresholds = []
                            for i in range(st.session_state.color_count):
                                color = st.color_picker(f'##### カラー{i+1}の設定', '#000000')
                                colors.append(color)
                                st.write('###### 以下から色の許容範囲（±）を指定できます。')
                                threshold_R = st.slider(f"R{i+1}", 0, 30, key=f"R_slider_{i}")
                                threshold_G = st.slider(f"G{i+1}", 0, 30, key=f"G_slider_{i}")
                                threshold_B = st.slider(f"B{i+1}", 0, 30, key=f"B_slider_{i}")
                                thresholds.append((threshold_R, threshold_G, threshold_B))
                            st.markdown('''<p class='box'>各素材のカラーを選択</p>''', unsafe_allow_html=True)
                            background1 = st.color_picker('###### 出力画像の背景カラーが変化します。', '#FFFFFF', key='back1')
                            #機能の実行
                            result_img1 = SelectionColor_Display_System(psd, colors, thresholds, background1)
                            st.markdown('''<p class='box2'>指定カラー表示システムの出力結果</p>''', unsafe_allow_html=True)
                            #出力画像の表示
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(psd_composite, caption='元イラスト', use_column_width=True)
                            with col2:
                                st.image(result_img1, caption='サポート結果', use_column_width=True)
                            result_buf1 = BytesIO()
                            result_img1.save(result_buf1, format='PNG')
                            result_buf1.seek(0)
                            #zipファイルに追加
                            zip_file.writestr('指定カラー表示システム.png', result_buf1.getvalue())
                    
                        #指定レイヤー輪郭表示システム
                        elif function == 'SelectionLayers_Contour_System':
                            st.markdown('''
                            <p class='my-text'>指定レイヤー輪郭表示システム</p>
                            <p class='box'>各値の調整</p>''', unsafe_allow_html=True)
                            threshold1 = st.slider('###### 二値化の閾値を調整できます。',0,255,128)
                            threshold2 = st.slider('###### 輪郭線の幅を調整できます。',1,10,3)
                            st.markdown('''<p class='box'>各素材の表示切替</p>''', unsafe_allow_html=True)
                            layer_display_switching = st.radio('###### レイヤーの表示・非表示を切り替えられます。', ('表示', '非表示'), horizontal=True)
                            background_display_switching = st.radio('###### 背景色の表示・非表示を切り替えられます。（非表示の場合、背景は透過されます。）', ('表示', '非表示'), horizontal=True)
                            st.markdown('''<p class='box'>各素材のカラーを選択</p>''', unsafe_allow_html=True)
                            support_color1 = st.color_picker('###### 輪郭線のカラーが変化します。', '#00FF00')
                            background2 = st.color_picker('###### 出力画像の背景カラーが変化します。', '#FFFFFF', key='back2')
                            st.markdown('''<p class='box'>表示する素材の選択</p>''', unsafe_allow_html=True)
                            #セッション変数の初期化（表示レイヤーの選択用）
                            if "selected_contours" not in st.session_state:
                                st.session_state.selected_contours = []
                            if "layers" not in st.session_state:
                                st.session_state.layers = None
                            selected_contours = st.multiselect(
                                '###### ～複数選択可能～',
                                name_list, 
                            )
                            st.write('###### :red[＊指定がない場合、線画レイヤーが自動で選択されます。]')
                            layers = Image.new("RGBA", psd_composite.size, (255, 255, 255, 0))
                            #選択レイヤーリストの合成
                            if not selected_contours:
                                layers = line_img
                            else:
                                #選択レイヤーが変更されていないかを確認
                                if selected_contours == st.session_state.selected_contours:
                                    layers = st.session_state.layers
                                else:
                                    for layer in psd.descendants():
                                        for item in selected_contours:
                                            if layer.name == item and not layer.is_group():
                                                layer_img = layer.composite()
                                                layers.paste(layer_img, (layer.left, layer.top), layer_img)
                                    #セッション変数を更新（表示レイヤーの選択用）
                                    st.session_state.selected_contours = selected_contours
                                    st.session_state.layers = layers
                            layers_resized = layers.resize((256, 256), Image.LANCZOS)
                            st.markdown('''<p class='box'>選択されたレイヤ</p>''', unsafe_allow_html=True)
                            st.image(layers_resized)
                            #機能の実行
                            result_img2 = SelectionLayers_Contour_System(psd, layers, threshold1, support_color1, threshold2, layer_display_switching, background_display_switching, background2)
                            st.markdown("""<p class='box2'>指定レイヤ輪郭表示システムの出力結果</p>""", unsafe_allow_html=True)
                            #出力画像の表示
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(psd_composite, caption='元イラスト', use_column_width=True)
                            with col2:
                                st.image(result_img2, caption='サポート結果', use_column_width=True)
                            result_buf2 = BytesIO()
                            result_img2.save(result_buf2, format='PNG')
                            result_buf2.seek(0)
                            #zipファイルに追加
                            zip_file.writestr('指定レイヤー輪郭表示システム.png', result_buf2.getvalue())
                        
                        #塗り漏れ検知システム１
                        elif function == 'MissingPaint_Detection_System1':
                            st.markdown('''
                            <p class='my-text'>塗り漏れ検知システム１</p>
                            <p class='box'>各値の調整</p>''', unsafe_allow_html=True)
                            line_scale = st.slider('###### 検知部分強調表示の強さを設定できます。', 1, 20, 1)
                            st.markdown('''<p class='box'>分割数の選択</p>''', unsafe_allow_html=True)
                            split_scale = st.radio('###### 出力画像の分割数を選択できます', [1, 4, 9, 16, 25, 36, 64], index=4, horizontal=True)
                            st.markdown('''<p class='box'>各素材の色を選択</p>''', unsafe_allow_html=True)
                            selected_color = st.radio('###### 出力画像の背景色を選択できます。', ['Red', 'Green', 'Blue'], horizontal=True)
                            #機能の実行
                            result_img3_list = MissingPaint_Detection_System1(psd, selected_color, split_scale, line_scale)
                            st.markdown('''<p class='box2'>塗り漏れ検知システム１の出力結果</p>''', unsafe_allow_html=True)
                            #出力画像の表示
                            cols = st.columns(5)
                            for i, img in enumerate(result_img3_list):
                                col = cols[i % 5]
                                resized_img = img.resize((300, 300), Image.Resampling.LANCZOS)
                                col.image(resized_img, use_column_width=True)
                                result_buf3 = BytesIO()
                                img.save(result_buf3, format='PNG')
                                result_buf3.seek(0)
                                #zipファイルに追加
                                name = "塗り漏れ検知システム１"
                                number = i
                                file_name = f'{name}_{number}.png'
                                zip_file.writestr(file_name, result_buf3.getvalue())
                            
                        #塗り漏れ検知システム２
                        elif function == 'MissingPaint_Detection_System2':
                            st.markdown('''
                            <p class='my-text'>塗り漏れ検知システム２</p> 
                            <p class='box'>各値の調整</p>''', unsafe_allow_html=True)
                            threshold4 = st.slider('###### 「塗り漏れ」と判定する色の許容誤差を調整できます。',0,20,3)
                            threshold5 = st.slider('###### 「塗り漏れ」判定箇所の円の半径を調整できます。',10,30,15)
                            threshold6 = st.slider('###### 「塗り漏れ」と判定する領域のサイズを調整できます。',100,1000,500)
                            st.markdown('''<p class='box'>各素材の色を選択</p>''', unsafe_allow_html=True)
                            support_color2 = st.color_picker('###### 「塗り漏れ」検出箇所の色が変化します。', '#FF00FF')
                            #機能の実行
                            result_img4 = MissingPaint_Detection_System2(psd, support_color2, threshold4, threshold5, threshold6)
                            st.markdown('''<p class='box2'>塗り漏れ検知システム２の出力結果</p>''', unsafe_allow_html=True)
                            #出力画像の表示
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(psd_composite, caption='元イラスト', use_column_width=True)
                            with col2:
                                st.image(result_img4, caption='サポート結果', use_column_width=True)
                            result_buf4 = BytesIO()
                            result_img4.save(result_buf4, format='PNG')
                            result_buf4.seek(0)
                            #zipファイルに追加
                            zip_file.writestr('塗り漏れ検知システム２.png', result_buf4.getvalue())
                        
                        #消し忘れ検知システム１
                        elif function == 'LineDrawingMistake_Detection_System1':
                            st.markdown('''
                            <p class='my-text'>消し忘れ検知システム１</p>
                            <p class='box'>各値の調整</p>''', unsafe_allow_html=True)
                            threshold3 = st.slider('###### 「消し忘れ」判定の細かさを調整できます。',1,300,200)
                            #機能の実行
                            result_img5 = LineDrawingMistake_Detection_System1(psd, line_img, threshold3)
                            st.markdown('''<p class='box2'>消し忘れ検知システム１の出力結果</p>''', unsafe_allow_html=True)
                            #出力画像の表示
                            col1, col2 = st.columns(2)
                            with col1:
                                st.image(psd_composite, caption='元イラスト', use_column_width=True)
                            with col2:
                                st.image(result_img5, caption='サポート結果', use_column_width=True)
                            result_buf5 = BytesIO()
                            result_img5.save(result_buf5, format='PNG')
                            result_buf5.seek(0)
                            #zipファイルに追加
                            zip_file.writestr('消し忘れ検知システム１.png', result_buf5.getvalue())
                        
                        #消し忘れ検知システム２
                        elif function == 'LineDrawingMistake_Detection_System2':
                            st.markdown('''<p class='my-text'>消し忘れ検知システム２</p>''', unsafe_allow_html=True)
                            #機能の実行
                            result_img6 = LineDrawingMistake_Detection_System2(psd, line_img)
                            if result_img6 == 0:
                                st.error('線画レイヤーが選択されていない、またはエラーイラストが入力されました。')
                            else:
                                st.markdown('''<p class='box2'>消し忘れ検知システム２の出力結果</p>''', unsafe_allow_html=True)
                                #出力画像の表示
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.image(psd_composite, caption='元イラスト', use_column_width=True)
                                with col2:
                                    st.image(result_img6, caption='サポート結果', use_column_width=True)
                                result_buf6 = BytesIO()
                                result_img6.save(result_buf6, format='PNG')
                                result_buf6.seek(0)
                                #zipファイルに追加
                                zip_file.writestr('消し忘れ検知システム２.png', result_buf6.getvalue())
                zip_buffer.seek(0)
                #ダウンロードボタンの表示
                st.download_button(
                    label="出力画像のダウンロードはこちらから",
                    data=zip_buffer, 
                    file_name="output_results.zip",
                    mime="application/zip",
                    type="primary"
                )
            else:
                st.error('機能が選択されていません。')