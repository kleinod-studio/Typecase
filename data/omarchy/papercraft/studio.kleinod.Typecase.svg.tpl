<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <!-- typecase-omarchy-icon: installed by tools/omarchy-icon.sh from the Typecase repository -->
  <title>Typecase</title>
  <desc>Typecase's logo in the theme's colors: two sheets of a manuscript, one behind the other, the front one with a heading in the main color, lines of text and a writing cursor, and a small cut gem in the corner, each piece with a hard shadow.</desc>
  <defs>
    <linearGradient id="main" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="{{ icon_main }}"/>
      <stop offset="1" stop-color="{{ icon_main_end }}"/>
    </linearGradient>
  </defs>
  <g transform="translate(256 256) scale(1.2) translate(-256 -256)">
    <!-- The sheet behind, a little higher and to the right. -->
    <rect x="152" y="64" width="268" height="328" rx="20" fill="{{ icon_shadow }}" transform="translate(0 8)"/>
    <rect x="152" y="64" width="268" height="328" rx="20" fill="{{ icon_paper }}"/>
    <rect x="152" y="64" width="268" height="328" rx="20" fill="{{ icon_shadow }}" opacity=".3"/>
    <!-- The sheet in front. -->
    <rect x="96" y="104" width="268" height="336" rx="20" fill="{{ icon_shadow }}" transform="translate(0 8)"/>
    <rect x="96" y="104" width="268" height="336" rx="20" fill="{{ icon_paper }}"/>
    <!-- The heading. -->
    <rect x="128" y="140" width="144" height="26" rx="13" fill="url(#main)"/>
    <!-- Lines of text, the last one short, where the cursor waits. -->
    <g fill="{{ icon_ink }}">
      <rect x="128" y="196" width="204" height="14" rx="7"/>
      <rect x="128" y="228" width="184" height="14" rx="7" opacity=".55"/>
      <rect x="128" y="260" width="204" height="14" rx="7" opacity=".55"/>
      <rect x="128" y="292" width="120" height="14" rx="7" opacity=".55"/>
    </g>
    <!-- The cursor. -->
    <rect x="260" y="280" width="16" height="40" rx="8" fill="{{ icon_shadow }}" transform="translate(0 6)"/>
    <rect x="260" y="280" width="16" height="40" rx="8" fill="{{ icon_mark }}"/>
    <!-- The gem: a cut stone seen from the front, its facets in the main color. -->
    <g transform="translate(330 330)">
      <polygon points="0,36 30,4 90,4 120,36 60,116" fill="{{ icon_shadow }}" transform="translate(0 8)"/>
      <polygon points="0,36 30,4 90,4 120,36 60,116" fill="url(#main)" stroke="{{ icon_paper }}" stroke-width="8" stroke-linejoin="round"/>
      <polygon points="30,4 90,4 76,36 44,36" fill="{{ icon_paper }}" opacity=".35"/>
      <polygon points="44,36 76,36 60,116" fill="{{ icon_shadow }}" opacity=".25"/>
    </g>
  </g>
</svg>
