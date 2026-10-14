<?php
/**
 * 픽담 운영 고정장치 (mu-plugin)  ―  2026-10-08
 *
 * 설치: 이 파일을  wp-content/mu-plugins/pickdam-core.php  로 업로드.
 *       (mu-plugins 폴더가 없으면 새로 만드세요. 이 폴더의 파일은 자동 활성화됩니다.)
 *       기존 rankmath-rest.php 는 그대로 두세요. 서로 간섭하지 않습니다.
 *
 * 왜 필요한가 — 수동으로 반복해야 했던 두 가지를 영구히 없앱니다.
 *   1) 사이트맵: Rank Math 는 사이트맵을 캐시에 저장하고, '값이 실제로 바뀐 설정 저장'이
 *      있어야만 캐시를 버립니다. 그래서 새 글을 올려도 사이트맵이 며칠씩 멈춰 있었습니다.
 *      → 캐시를 끕니다. 글 36편 규모에서 생성 비용은 무시할 수준입니다.
 *   2) IndexNow: 키 파일이 하위 폴더에 있으면 그 폴더 아래 주소만 승인되어(실측 422)
 *      글 주소 즉시 등록이 전부 거부됩니다. 키 파일은 사이트 최상위에 있어야 합니다.
 *      → 최상위 경로를 워드프레스가 직접 응답합니다. 파일을 따로 올릴 필요가 없습니다.
 *   3) 덤: 페이지(page)에도 Rank Math 메타를 REST 로 쓸 수 있게 등록합니다.
 *      (기존 파일은 글(post)만 등록해 소개·문의 페이지의 SEO 제목을 자동화할 수 없었습니다.)
 */

if (!defined('ABSPATH')) {
    exit;
}

/* ── 1) 사이트맵 캐시 비활성 ───────────────────────────────────────────── */
add_filter('rank_math/sitemap/enable_caching', '__return_false');

/* ── 2) IndexNow 키를 사이트 최상위에서 응답 ──────────────────────────── */
define('PICKDAM_INDEXNOW_KEY', '3073d0f9a62c8f5aa955b604ff3ed520');

add_action('init', function () {
    $key  = PICKDAM_INDEXNOW_KEY;
    $uri  = isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '';
    $path = parse_url($uri, PHP_URL_PATH);
    if ($path !== '/' . $key . '.txt') {
        return;
    }
    nocache_headers();
    status_header(200);
    header('Content-Type: text/plain; charset=UTF-8');
    header('X-Robots-Tag: noindex');
    echo $key;
    exit;
}, 1);

/* ── 3) 페이지에도 Rank Math 메타 REST 등록 ───────────────────────────── */
add_action('init', function () {
    $keys = array(
        'rank_math_focus_keyword',
        'rank_math_description',
        'rank_math_title',
    );
    foreach ($keys as $key) {
        register_post_meta('page', $key, array(
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => 'string',
            'auth_callback' => function () {
                return current_user_can('edit_pages');
            },
        ));
    }
});

/* ── 4) 피드는 색인 대상이 아니다 (2026-10-13) ────────────────────────
 * 마크토 실측: 구글 서치콘솔 미색인 목록에 글별 RSS 피드와 댓글 피드가 잡혀
 * 숫자만 부풀리고 있다(/…/feed/ 와 /comments/feed/ 둘 다 HTTP 200).
 * robots.txt 로 막으려 했으나 서버에 실제 robots.txt 파일이 있어 Rank Math
 * 편집기가 잠겨 있다(실측: "robots.txt 파일을 쓸 수 없습니다").
 * 그래서 헤더로 처리한다 — Disallow 는 '차단됨'으로 남지만 noindex 는 색인에서
 * 실제로 빠진다. 사이트 전체 /feed/ 는 WebSub 통지에 쓰므로 그대로 둔다.
 */
add_action('template_redirect', function () {
    if (!is_feed()) {
        return;
    }
    $path = parse_url(isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '', PHP_URL_PATH);
    if ($path === '/feed/' || $path === '/feed') {
        return;   // 사이트 전체 피드는 유지
    }
    header('X-Robots-Tag: noindex, follow', true);
}, 1);

/* ── 5) 쿠팡 카드 클릭·노출을 GA4 이벤트로 기록 (2026-10-14) ──────────
 * 왜: 파트너스 클릭이 0인데 원인이 '안 보여서'인지 '보고도 안 눌러서'인지
 *     구분할 수가 없었다. 2026-10-14 에 카드를 2~3화면 아래에서 1.4~1.8화면으로
 *     올렸는데, 그 효과를 숫자로 보려면 **본 사람**과 **누른 사람**을 따로 세야 한다.
 * 본문에 <script> 를 넣는 길은 막혀 있다 — 호스트 WAF(NinjaFirewall)가 REST 본문에
 * '<script' 가 있으면 요청을 통째로 버린다(2026-10-04 실측). 그래서 플러그인이
 * 서버에서 직접 출력한다.
 * 보내는 이벤트: coupang_click(placement=card|inline) · coupang_card_view(글당 1회)
 */
add_action('wp_footer', function () {
    if (is_admin() || is_feed()) {
        return;
    }
    ?>
<script id="pickdam-coupang-track">
(function () {
  function send(name, params) {
    if (typeof window.gtag === 'function') { window.gtag('event', name, params); }
  }
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest) { return; }
    var a = t.closest('a[href*="coupang"]');
    if (!a) { return; }
    send('coupang_click', {
      placement: a.closest('.pick-product') ? 'card' : 'inline',
      link_text: (a.textContent || '').trim().slice(0, 60),
      page_path: location.pathname
    });
  }, true);
  if (!('IntersectionObserver' in window)) { return; }
  var fired = false;
  var io = new IntersectionObserver(function (entries) {
    for (var i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting || fired) { continue; }
      fired = true;
      send('coupang_card_view', { page_path: location.pathname });
      io.disconnect();
    }
  }, { threshold: 0.5 });
  var cards = document.querySelectorAll('.pick-product');
  for (var i = 0; i < cards.length; i++) { io.observe(cards[i]); }
})();
</script>
    <?php
});
