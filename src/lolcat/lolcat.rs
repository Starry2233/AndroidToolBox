use std::{env, io};
mod shared;
use shared::file_lolcat;

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        eprintln!("Usage: lolcat <file>");
        std::process::exit(1);
    }
    let path = &args[1];
    match file_lolcat(path) {
        Ok(output) => print!("{}", output),
        Err(e) => eprintln!("Error: {}", e),
    }
    Ok(())
}
