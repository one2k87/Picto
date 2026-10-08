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
