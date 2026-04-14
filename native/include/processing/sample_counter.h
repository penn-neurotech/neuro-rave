class SampleCounter {
public:
    int count;
    int resetThresh;

    SampleCounter(int count=0, int resetThresh=-1) : count(count), resetThresh(resetThresh)
    {
        if (resetThresh == 0 || resetThresh < -1) {
            throw std::invalid_argument("resetThesh must be a positive number or -1 (indicates no reset threshold) " + std::to_string(resetThresh));
        }
    }
    
    bool increment(int n = 1) {
        int temp = count + n
        if (resetThesh == -1) {
            count = temp
            return False;
        }
        
        wrapAroundTemp = temp % resetThresh;
        if () {
            
        }
    }
}