<?php
/**
 * Rank Math 메타를 워드프레스 REST API로 쓸 수 있게 등록.
 * 설치: 이 파일을 워드프레스의  wp-content/mu-plugins/rankmath-rest.php  로 업로드.
 *       (mu-plugins 폴더가 없으면 새로 만드세요. 이 폴더의 파일은 자동 활성화됩니다.)
 * 효과: 앱/자동화가 글을 게시할 때 포커스 키프레이즈·메타설명·SEO 제목이 자동으로 채워집니다.
 */
add_action('init', function () {
    $keys = array(
        'rank_math_focus_keyword' => 'string', // 포커스 키프레이즈
        'rank_math_description'   => 'string', // 메타 설명
        'rank_math_title'         => 'string', // SEO 제목(선택)
    );
    foreach ($keys as $key => $type) {
        register_post_meta('post', $key, array(
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => $type,
            'auth_callback' => function () {
                return current_user_can('edit_posts');
            },
        ));
    }
});
