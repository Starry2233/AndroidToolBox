use std::io::Read;

fn hsv_to_rgb(h: f32, s: f32, v: f32) -> (u8, u8, u8) {
    let c = v * s;
    let x = c * (1.0 - ((h / 60.0) % 2.0 - 1.0).abs());
    let m = v - c;

    let (r, g, b) = match h {
        h if h < 60.0 => (c, x, 0.0),
        h if h < 120.0 => (x, c, 0.0),
        h if h < 180.0 => (0.0, c, x),
        h if h < 240.0 => (0.0, x, c),
        h if h < 300.0 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };

    (
        ((r + m) * 255.0) as u8,
        ((g + m) * 255.0) as u8,
        ((b + m) * 255.0) as u8,
    )
}

pub fn string_lolcat(s: &str) -> String {
    let mut line = 0;
    let mut result = String::new();
    const PINK_HUE_OFFSET: f32 = 340.0;
    for l in s.lines() {
        for (i, ch) in l.chars().enumerate() {
            let hue = ((i as f32 * 8.0) + (line as f32 * 12.0) + PINK_HUE_OFFSET) % 360.0;
            let (r, g, b) = hsv_to_rgb(hue, 1.0, 1.0);

            result.push_str(&format!("\x1b[38;2;{};{};{}m{}", r, g, b, ch));
        }
        result.push_str("\x1b[0m\n");
        line += 1;
    };
    result
}

pub fn file_lolcat(path: &str) -> std::io::Result<String> {
    let mut file = std::fs::File::open(path)?;
    let mut contents = String::new();
    file.read_to_string(&mut contents)?;
    Ok(string_lolcat(&contents))
}
